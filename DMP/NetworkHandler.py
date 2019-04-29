import os
import socket
import time
import queue
import asyncio
try:
    import netifaces 
except ModuleNotFoundError:
    os.system('pip install netifaces')
import threading
from threading import Event
import pickle
from queue import Queue
from aClient import Client
from aServer import Server
class NetworkHandler:
    def __init__(self, infoQ, serverQ, func_stream_next, port = 25011, busy = threading.Event(),
        remote_play_event = Event(), pause_event = Event()):
        print('netHandler')
        self.port = port
        self.recvQ = Queue(1)
        self.recvQ.put({})
        self.serverQ = serverQ
        self.infoQ = infoQ
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.shutdown = threading.Event()
        self.remote_play_event = remote_play_event
        self.pause_event = pause_event
        self.func_stream_next = func_stream_next
        self.busy = busy
        threading.Thread(target = self.start_server).start()
        self.addr_list = []
        self.all_ip=[]
        self.IPV4 = '' 
        self.broadcast = ''
        self.scan_thread = threading.Thread(target = self.get_network_info)
        self.monitor_thread = threading.Thread(target = self.monitor)
        self.monitor_thread.start()
        self.scan_thread.start()

        #self.get_network_info(self.ready)
        #self.get_network_info()
        #time.sleep(100)

    def start_server(self):
        #print('server started')
        asyncio.set_event_loop(self.loop)
        #print('loop looped')
        #try:
        S=Server(self.serverQ, self.infoQ, self.recvQ, self.func_stream_next, self.port,
            self.remote_play_event, self.shutdown, self.pause_event)
        #except:
            #print('error in starting server')

    def close_server(self):
        print('closing server')
        print('addr_list', self.addr_list)
        for addr in self.addr_list:
            print('closing',addr)
            C = Client(self.infoQ, addr, self.port)
            C.send_close()
        self.shutdown.set()
        return True

    def monitor(self):
        #print('net monitor initilized')
        #try:
        while not self.shutdown.is_set():
            self.busy.wait()
            server_info = self.serverQ.get()
            if len(server_info['remove'])>0:
                for addr in server_info['remove']:
                    print('removing', addr)
                    self.addr_list.remove(addr)
                server_info['remove'] = []
            self.serverQ.put(server_info)

            #method 2 #TODO, send signal if list changes
            #print('addr_list', self.addr_list)
            rem_list = []
            for addr in self.addr_list:
                C = Client(self.infoQ, addr, self.port)
                if not C.get_pulse():
                    rem_list.append(addr)
            for addr in rem_list:
                self.busy.clear()
                recvData = self.recvQ.get()
                del recvData[addr]
                self.addr_list.remove(addr)
                self.recvQ.put(recvData)
                self.busy.set()
                print('done removing from network handler', rem_list)
            time.sleep(10)
            
       # except IOError:
        #    print('error in monitor')

    def get_network_info(self):
        #print('get net info')
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(.5)
        try:
            s.connect(("8.8.8.8", 80))#try calling google
            self.IPV4 = s.getsockname()[0]
            print('IPV4:', self.IPV4)
        except:
            print('failure to connect to the internet')
        # try: 
        #     host_name = socket.gethostname() 
        #     host_ip = socket.gethostbyname(host_name)
        #     #print('Hostname :  ',host_name) 
        #     #print('IP : ',host_ip) 
        # except: 
        #     print('Unable to get Hostname and IP') 
        ifaces = netifaces.interfaces()
    
        for iface in ifaces:
            try:
                if self.shutdown.is_set():
                    return #kill the thread
                ip = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr']
                #print(ip)
                self.all_ip.append(ip)
                if ip == self.IPV4:
                    print(netifaces.ifaddresses(iface)[netifaces.AF_INET][0])
                    if 'broadcast' in netifaces.ifaddresses(iface)[netifaces.AF_INET][0]:
                        self.broadcast = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['broadcast']
                        #print('broadcast:', self.broadcast)
                    if 'netmask' in netifaces.ifaddresses(iface)[netifaces.AF_INET][0]:
                        self.netmask = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['netmask']
                        #print('netmask:', self.netmask)
                    #break #no need to look further
                    #print(self.addr_list)
                #print(f'IP: {ip} from Interface {iface}')
            except:
                pass
        base_address = ''
        start_address = 0
        end_address = 255
        addr_segs = self.IPV4.split('.')
        mask_segs = self.netmask.split('.')
        for b in range(len(addr_segs)): 
            nSeg = int(mask_segs[b])
            if nSeg == 255:
                if len(base_address) != 0:
                    base_address+='.'
                base_address+=addr_segs[b]
                continue
            aSeg = int(addr_segs[b])
            start_address = aSeg & nSeg 
            #print('base address', start_address)
            
            end_address = int(aSeg | (nSeg ^ 255))
            #print('top address', end_address)
        
        for a in range(start_address, end_address):
            if self.shutdown.is_set():
                    return #kill the thread
            full_address = base_address+'.'+str(a)
            if self.port_scan(full_address):
                self.addr_list.append(full_address)
        self.ready.set()
        print('scan done')
        
    def port_scan(self, addr):
        #print('trying:', addr)
        for ip in self.all_ip:#skip your own address
                if ip == addr:
                    return False
        C = Client(self.infoQ, addr, self.port)
        if C.get_port_open():
            print('port scan found:',addr)  
            recv_data = self.recvQ.get()
            recv_data[addr] = C.recvData
            self.recvQ.put(recv_data)
            return True  
        return False

    def remote_play_request(self, addr, title):
        C = Client(self.infoQ, addr, self.port) #client closes when done
        C.send_play_req(self.IPV4, title)  

    def send_client(self, addr, data, size):
        C = Client(self.infoQ, addr, self.port) #client closes when done
        C.send_pickle(size, data)
        
    def send_client_m(self, addr, data_array, waitOn):
        C = Client(self.infoQ, addr, self.port) #client closes when done
        C.send_multi_pickle(data_array, waitOn)
        
    def send_serialized_to_all(self, size, data):
        for addr in self.addr_list:
            print('trying:', addr)
            try:
                threading.Thread(target=self.send_client, args=[addr,data,size]).start()
            except:
                print('Unable make connection to send')

    def send_serialized_to_specific(self, addr_list, data_array, waitOn):
        print(addr_list)
        all_threads = []
        for addr in addr_list:
            print('trying:', addr)
            try:
                thread = threading.Thread(target=self.send_client_m, args=[addr,data_array,waitOn])
                thread.start()
                all_threads.append(thread)
            except:
                print('Unable make connection to send')
        for thread in all_threads:
            thread.join()
        print('all send threads joined')

    def send_serialized_to_all_m(self, data_array, waitOn):
        print(self.addr_list)
        all_threads = []
        for addr in self.addr_list:
            print('trying:', addr)
            try:
                thread = threading.Thread(target=self.send_client_m, args=[addr,data_array,waitOn])
                thread.start()
                all_threads.append(thread)
            except:
                print('Unable make connection to send')
        for thread in all_threads:
            thread.join()
        print('all send threads joined')
            
                
if __name__ == '__main__':
    NetworkHandler()
