import requests
import socket
import socks

response_before_tor = requests.get("http://httpbin.org/ip", timeout=10) #real_ip_adress
real_ip=response_before_tor.json()["origin"]
print("real_ip: ",real_ip) 

# Configure Python to use Tor SOCKS Proxy (Default Port 9050)
socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
socket.socket = socks.socksocket


response_after_tor = requests.get("http://httpbin.org/ip", timeout=10) #tor_ip_adress
tor_ip=response_after_tor.json()["origin"]
print("tor_ip: ",tor_ip)
if response_before_tor != response_after_tor : 
    print("conection established") 
else : 
    print("an error occured")
