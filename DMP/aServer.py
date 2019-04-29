from socket import *
import asyncio
import os
import zlib
import threading
from threading import Event
import queue
import pickle
try:
    from pygame import mixer
except ModuleNotFoundError:
    os.system('pip install pygame')


class Server:
    def __init__(self, serverQ, infoQ, recvQ, func_stream_next, port,
        remote_play_event = Event(), shutdown = Event(), pause_event = Event()):
        loop = asyncio.get_event_loop()
        self.infoQ = infoQ
        self.serverQ = serverQ
        self.recvQ = recvQ
        self.func_stream_next = func_stream_next
        self.remote_play = remote_play_event
        self.data = []
        self.playthread = None
        try:
            loop.run_until_complete(self.echo_server(('', port), loop, shutdown, pause_event))
        except ConnectionResetError:
            print('connection closed')

    def lists_to_dic(self, key_list, data_list):
        dictionary = {}
        for iKey in range(len(key_list)):
            dictionary[key_list[iKey]] = data_list[iKey]
            #print(dictionary)
        return dictionary
            
    def play_stream(self,recvdQ, datAvail, shutdown, pause_event, client):
        mixer.init()
        channel = None
        hasLock = False
        end = False
        self.remote_play.set()
        print('playstream active')
        while self.remote_play.is_set() and not shutdown.is_set():#if flag cleared this will hault playback
            #print('playing')
            #print('sample:',data[0:99],len(data))
            if not pause_event.is_set():#stops when user requests pause
                mixer.pause()
                pause_event.wait()
                mixer.unpause()
            if not hasLock:
                #print('wait on datavail')
                hasLock = datAvail.acquire()
                #print('datavail aquired')
            try:
                if recvdQ.full():
                    if channel is None:
                        recvd = recvdQ.get()
                        if len(recvd) > 0:
                            data = recvd.pop(0)
                            recvdQ.put(recvd)
                            if data == 'end' and not channel.get_busy():
                                hasLock = False
                                datAvail.release()
                                break
                            sound = mixer.Sound(buffer = data)
                            #print('first sound buffed')
                            channel = sound.play()
                            channel.pause()
                            hasLock = False
                            datAvail.release()
                        else:
                            #print('wait on data - init')
                            recvdQ.put(recvd)
                            datAvail.wait()
                            #print('init awkoen')
                    else:
                        if not channel.get_queue(): 
                            recvd = recvdQ.get()
                            if len(recvd) > 0 and not end:
                                #print('addnl sound buffed',len(recvd), 'available' )
                                data = recvd.pop(0)
                                recvdQ.put(recvd)
                                #print(data[:2])
                                if data == 'end':
                                    #print('!!!')
                                    end = True
                                if end and not channel.get_busy():
                                    #print('end play')
                                    break
                                channel.queue(mixer.Sound(buffer = data))
                                channel.unpause()
                                hasLock = False
                                datAvail.release()
                            elif end:
                                while True:
                                    #print('addnl sound buffed',len(recvd), 'available' )
                                    data = recvd.pop(0)
                                    channel.queue(mixer.Sound(buffer = data))
                                    channel.unpause()
                                    if not channel.get_busy():
                                       break
                                    recvdQ.put(recvd)
                                    hasLock = False
                                    datAvail.release()
                                    break
                            else:
                                recvdQ.put(recvd)
                                #print('wait on data')
                                datAvail.wait()
                                #print('data awoken')
                        else:
                            #print('wait on queue')
                            hasLock = False
                            datAvail.release()
            except Exception as e: 
                print(e)
                hasLock = False
                datAvail.release()
                pass
        if channel is not None:
            if channel.get_busy():
                channel.stop()
        print('termination our of loop')
        self.remote_play.clear()
        recvd = recvdQ.get()#clear the recieved in case user terminated
        if recvdQ is []:#naturally terminated
            self.func_stream_next() #calls passed function from GUI to play next song
        else:
            print('sending stopper')
            client.sendall(b'S')
            client.close()
        recvdQ.put([])
        recvdQ.put(recvd)
        
                    
    async def echo_server(self, address, loop, shutdown, pause_event):
        S = socket(AF_INET, SOCK_STREAM)
        S.bind(address)
        S.listen(1)
        S.setblocking(False)
        while not shutdown.is_set():
            client, addr = await loop.sock_accept(S)
            addr = addr[0]#we dont want to include port
            #print('Connection from', addr)
            try:
                loop.create_task(self.echo_handler(addr,client,loop,shutdown,pause_event))
            except ConnectionResetError: #client force closed
                server_info = self.serverQ.get()
                print('forced term', addr)
                server_info['remove'].append(addr)
                self.serverQ.put(server_info)


    async def echo_handler(self, addr, client, loop, shutdown, pause_event):
        try:
            played_thread = False
            sdata = b''
            end = False
            notify = False
            hasLock = False
            recvdQ=queue.Queue(1)
            recvdQ.put([])
            datAvail = threading.Condition(threading.Lock())
            while not shutdown.is_set():
                if not end:
                    hasLock = datAvail.acquire(blocking=True)
                    #print('got datavail', hasLock)
                else:
                    while not shutdown.is_set():
                        datAvail.acquire()
                        #print('renotify')
                        datAvail.notify()
                        datAvail.release()
                        recvd = recvdQ.get()
                        if len(recvd) == 0:
                            recvdQ.put(recvd)
                            break
                        recvdQ.put(recvd)
                        #print('release')
                    #print('end reached')
                    hasLock = datAvail.acquire(blocking=True)
                data = await loop.sock_recv(client,10000)
                
                if not data:
                    self.remote_play.clear()
                    break
                #print('packet recieved')
                clean_data = pickle.loads(data)
                if len(clean_data) < 2:
                    #one line commands
                    if clean_data[-1] == 'P': #pulse check connection
                        client.sendall(b'T')
                        #print('sent terminator')
                        sdata = b''
                    elif clean_data[-1] == 'eof':
                        self.data = clean_data[:-1]
                        print('eof')
                        print('sending terminator')
                        client.sendall(b'T')  
                    elif clean_data[-1] == 'ter': #terminate connection
                        server_info = self.serverQ.get()
                        print('term recieved from', addr)
                        server_info['remove'].append(addr)
                        self.serverQ.put(server_info)
                        client.sendall(b'T')
                        print('sent terminator')
                        sdata = b''
                        break
                    else:
                        print(clean_data)
                    
                else:
                    if clean_data[-2] == 'end':
                        sdata = 'end'
                        print('end rcvd')
                        end = True
                        
                    elif clean_data[-1] == 'eop':#end of part
                        #print('appending',type(clean_data[1]))
                        sdata = sdata + clean_data[1]
                        client.sendall(b'T')
                        
                    #print(len(sdata))
                    #print('pos:',mixer.music.get_pos())
                    elif clean_data[-1] == 'eos':#end of segment
                        sdata = sdata + clean_data[1]
                        if played_thread == False:
                            played_thread = True
                            #print('starting thread')
                            #self.playthread.join() #if you want the least one to end first
                            self.playthread = threading.Thread(target=self.play_stream,
                                        args=[recvdQ,datAvail,shutdown,pause_event,client])
                            self.playthread.start()
                        #print('rcvd')
                        sdata=zlib.decompress(sdata)
                        recvd = recvdQ.get(block=True)
                        recvd.append(sdata)
                        recvdQ.put(recvd)
                        if hasLock:
                            notify = True   
                        sdata = b''
                        client.sendall(b'T')
                        
                    #info request
                    elif clean_data[-1] == 'req':
                        dictionary = self.lists_to_dic(clean_data[0], clean_data[1])
                        recvData = self.recvQ.get()
                        recvData[addr] = dictionary
                        print('recvd', dictionary) #should be all info from attache
                        self.recvQ.put(recvData)
                        info = self.infoQ.get()
                        #infoQ contains netList|titleList|fileTitle(if streaming)
                        print('echo_server has infoQ')
                        deviceName = [info['deviceName']]
                        playlist = [str(k) for k in info['titleList']]#load from above to send out
                        sendInfo = pickle.dumps(deviceName + playlist + ['T'])
                        if addr not in info['netList']: #0 index is netlist
                            info['netList'].append(addr)
                        self.infoQ.put(info)
                        print('echo_server dropped infoQ')
                        #print('sending sendInfo')
                        client.sendall(sendInfo)#sendinfo contains T
                        sdata = b''
                        
                    #play request
                    elif clean_data[-1] == 'prq':
                        #print('recvd', clean_data) #title and address to send to 
                        server_info = self.serverQ.get()
                        print(clean_data[0:-1])
                        server_info['requests'].append(clean_data[0:-1])
                        self.serverQ.put(server_info)
                        client.sendall(b'T')
                        sdata = b''

                #print('end loop')
                if hasLock:
                    if notify:
                        datAvail.notify()
                    datAvail.release()
                    #print('did release')
                #print(clean_data, len(clean_data),clean_data[len(clean_data)-1])
                #signals device leaving net
            self.playthread = None
            if played_thread == True:
                self.func_stream_next()
            #print('Connection closed')
            client.close()
        except ConnectionAbortedError:
            pass #we don't need to handle this, jsut close this async op
        except ConnectionResetError:
            pass #remote host unexpectedly gone
        except OSError:
            pass #not sure what causes the error but passing works since the connection closes

if __name__ == '__main__':
    def dummy():
        True
    rq = queue.Queue(1)
    sq = queue.Queue(1)
    iq = queue.Queue(1)
    rq.put({})
    sq.put({'remove':[], 'requests': [] })
    iq.put({'netList':[],'titleList':['lorem ipsum','greeking'],'deviceName':'Pi'})
    s=Server(sq,iq,rq,dummy,25011)
# if __name__ == '__main__':
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(echo_server(('',25000), loop))

#source https://www.youtube.com/watch?v=R0XrNFvBRso
