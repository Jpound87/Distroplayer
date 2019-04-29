
from socket import *
import pickle
import time

#todo: timeout
class Client:
    def __init__(self, infoQ, host='',port=25011):
        self.S = socket(AF_INET, SOCK_STREAM)
        self.infoQ = infoQ
        self.recvData = {}
        self.host = host
        self.port = port

    def get_pulse(self):
        #print('sending pulse')
        try:
            self.S.settimeout(1)
            self.S.connect((self.host,self.port))
            self.S.send(pickle.dumps(['P']))
            reply = self.S.recv(10000)
            reply = reply.decode()
            if reply == 'T':
                #print('terminator recieved', self.host)
                return True
            self.S.close()
            return False
        except timeout:
            print(self.host, 'pulse fail')
            return False #this is actually the detection of link failure

    def send_close(self):
        print('sending ter')
        self.S.settimeout(5)
        self.S.connect((self.host,self.port))
        self.S.send(pickle.dumps(['ter']))
        reply = self.S.recv(10000)
        reply = reply.decode()
        if reply == 'T':
            print('terminator recieved', self.host)
            return True
        self.S.close()
        print('closed connection with', self.host)
    
    def send_play_req(self, recv_addr, title):
        print('sending request for', title)
        self.S.settimeout(10)
        self.S.connect((self.host,self.port))
        self.S.send(pickle.dumps([recv_addr]+[title]+['prq']))
        reply = self.S.recv(10000)
        reply = reply.decode()
        if reply == 'T':
            print('closed connection with', self.host)
            self.S.close()
            return True

    def get_port_open(self):
        self.S.settimeout(.1)
        try:
            #print(self.host)
            self.S.connect((self.host, self.port))
            self.S.send(pickle.dumps(['eof']))
            fail_count = 0
            while True: 
                reply = self.S.recv(1000)
                reply = reply.decode()
                print(reply)
                if reply == 'T':
                    print('found', self.host)
                    self.xfer_data()
                    print('returning true')
                    return(True)
                elif fail_count == 1:
                    print('connection broken')
                    self.S.close()
                    return(False)
                fail_count += 1
                #print(fail_count)
        except timeout:
            pass #likely noconnection
        except Exception as e: print(e)
    
    #converts dict to serializable lists, converted back 
    #once recieved
    def dict_to_lists(self, dictionary): 
            key_list = [str(k) for k in dictionary]
            data_list = []
            for key in key_list:
                #print('!key', type(dictionary[key]))
                if type(dictionary[key]) is list:
                    data_list.append([i for i in dictionary[key]])
                if type(dictionary[key]) is type({}.keys()):
                    data_list.append([str(i) for i in dictionary[key]])
                if type(dictionary[key]) is str:
                    data_list.append([dictionary[key]])
                #print(key_list, data_list)
            return key_list, data_list

    def xfer_data(self):
        print('xfer data')
        #try: #already in try
        self.S.settimeout(None)
        info = self.infoQ.get()
        print('xfer have Q')
        key_list, data_list = self.dict_to_lists(info)
        self.infoQ.put(info)
        print('xfer drop Q')
        #send our name
        self.S.send(pickle.dumps([key_list]+[data_list]+['req']))
           
        fail_count = 0
        while True: 
            data = self.S.recv(10000)
            print(data)
            clean_data = pickle.loads(data)
            if clean_data[-1] == 'T':
                self.recvData['deviceName'] = [clean_data[0]]
                self.recvData['titleList'] = clean_data[1:-1]
                print('data:',clean_data)
                break
            elif fail_count == 5:
                print('connection broken')
                break
            fail_count += 1
            #print(fail_count)
        #except:
            #print('failure in get_playlist')
        self.S.close()
        print('xfer complete')

    def send_multi_pickle(self, data_array, waitOn):
        # host = '192.168.1.143'
        # port = 25000
        #print('connecting')
        self.S.settimeout(30)
        try:
            self.S.connect((self.host, self.port))
            print(len(data_array), 'segments')
            for data in data_array:
                size = len(data)
                print('sending segment')
                step = 0
                while step <= size:
                    if (step+1023>=size):
                        self.S.send(pickle.dumps([size, data[step:size], 'eos']))#end of segment
                        #print('sent eos')
                    else:
                        self.S.send(pickle.dumps([size, data[step:step+1023], 'eop']))#end of part
                        #print('sent packet', step, 'of' , size)
                    reply = self.S.recv(10000)
                    reply = reply.decode()
                    if reply == 'T':
                        step = step+1023
                    elif reply =='S':
                        self.S.close()
                        print('stream stopped')
                    #fail_count = 0
            self.S.send(pickle.dumps([0, 'end', 'eos']))     
                    #print(fail_count)
            
            #if waitOn:
                #print('waiting')
                #time.sleep(120)
            print('all sent')
            self.S.close()
        except:
            self.S.close()
            pass

    def send_pickle(self, size, data):
        # host = '192.168.1.143'
        # port = 25000
        #print('connecting')
        self.S.settimeout(30)
        try:
            self.S.connect((self.host, self.port))
            self.S.send(pickle.dumps([size, data, 'eof']))
            fail_count = 0
            while True: 
                reply = self.S.recv(10000)
                reply = reply.decode()
                print(reply)
                if reply == 'T':
                    print('recieved terminator')
                    return(True)
                if fail_count == 10:
                    print('connection broken')
                    return(False)
                fail_count += 1
                #print(fail_count)
            self.S.close()
        except:
            self.S.close()
            pass
        
#C = Client('192.168.1.196',25000)  
#C.send_pickle(['a','b','c','eof'])  
if __name__ == '__main__':
    c=Client('192.168.1.143', 25011)
    c.get_port_open()
 
