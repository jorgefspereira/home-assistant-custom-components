# home-assistant-custom-components

My custom components for http://www.home-assistant.io

Components List
---------------

 * [Samsung Air Conditioner Climate Component](#samsung-climate-component)

## Samsung Air Conditioner Climate Component

This allows you to control your samsung air conditioner basic functions: on/off, target temperature, mode (heat, cool, dry, ...)

This project is based on awesome work of cicciovo - https://github.com/cicciovo/homebridge-samsung-airconditioner

IMPORTANT: The component only works with samsung air conditioners that allow communication through port 8888.

### Installation

- Copy file `climate/samsung.py` to your `ha_config_dir/custom_components/climate` directory.
- Copy file `ac14k_m.pem` to your `ha_config_dir` directory. 
- Add to your `ha_config_dir/configuration.yaml` the config below.
- Restart Home-Assistant.

NOTE: Assign static IP address to your AC (check your router settings to do that).

### Configuration

```yaml

climate:
  - platform: samsung
    devices:
      - name: Office
        host: *****
        port: 8888
        token: *****
      - name: Living Room
        host: *****
        port: 8888
        token: *****

```

Configuration variables:

- **name** (*Optional*): Name of the device. (default = "RAC")
- **host** (*Required*): The IP address of the air conditioner.
- **port** (*Required*): The port used to communicate with the device.
- **token** (*Required*): Token used to authorize the requests.

### Token

To obtain a token for your samsung air conditioner do the following:

- Turn OFF your AC
- Find the ip address of your ac.
- Run `python Server8889.py`
- Open another shell and run `curl -k -H "Content-Type: application/json" -H "DeviceToken: xxxxxxxxxxx" --cert /path_to_pem/ac14k_m.pem --insecure -X POST https://IP_ADDRESS:8888/devicetoken/request` with the right values for `path_to_pem` and `IP_ADDRESS`
- Turn ON your AC
- Check the shell running the file Server8889.py...it should appear the TOKEN.

### Confirmed compatibility list (model numbers)

- AR09KSWSBWKNET
- AR12KSWSBWKNET


