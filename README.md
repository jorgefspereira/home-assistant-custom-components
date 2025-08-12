# Samsung RAC Climate Component

This allows you to locally control your samsung air conditioner basic functions: 
  - on/off 
  - target temperature 
  - mode (heat, cool, dry, ...)

IMPORTANT: The component only works with samsung air conditioners that allow communication through port 8888.

### Installation

#### HACS (Home Assistant Community Store)

1. If HACS is not installed yet, download it following the instructions on https://hacs.xyz/docs/setup/download/
2. Proceed to the HACS initial configuration following the instructions on https://hacs.xyz/docs/configuration/basic
3. On your sidebar go to HACS.
4. Click on the 3 dots button at the top right corner.
5. Add this repository url as an integration type.
6. Go back on your HACS dashboard and download the Samsung Climate

### Configuration

1. Go to Home Assistant Settings > Devices & Services > Devices
2. Click Add device at bottom right corner
3. Search for Samsung climate and click enter
4. And fill the required params:
    ```
      name: "Living Room AC"
      host: "rac_local_ipaddress"
      port: "8888"
      token: "your_token_here"
      cert_path: "ac14k_m.pem" 
    ```
### Token

To obtain a token for your samsung air conditioner do the following:

1. Turn OFF your AC
2. Find the ip address of your ac.
3. Run `python2 Server8889.py`
4. Open another shell and run `curl -k -H "Content-Type: application/json" -H "DeviceToken: xxxxxxxxxxx" --cert /path_to_pem/ac14k_m.pem --insecure -X POST https://IP_ADDRESS:8888/devicetoken/request` with the right values for `path_to_pem` and `IP_ADDRESS`
5. Turn ON your AC
6. Check the shell running the file Server8889.py...it should appear the TOKEN.

### Confirmed compatibility list (model numbers)

- AR09KSWSBWKNET
- AR12KSWSBWKNET


