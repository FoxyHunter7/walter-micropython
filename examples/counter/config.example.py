from walter_modem.enums import WalterModemPDPAuthProtocol

CELL_APN = ''
"""
The cellular Access Point Name (APN).
Leave blank to enable automatic APN detection, which is sufficient for most networks.
Manually set this only if your network provider specifies a particular APN.
"""

APN_USERNAME = ''
"""
The username for APN authentication.
Typically, this is not required and should be left blank.
Only provide a username if your network provider explicitly mandates it.
"""

APN_PASSWORD = ''
"""
The password for APN authentication.
This is generally unnecessary and should remain blank.
Set a password only if it is specifically required by your network provider.
"""

AUTHENTICATION_PROTOCOL = WalterModemPDPAuthProtocol.NONE
"""
The authentication protocol to use if requiren.
Leave as none when no username/password is set.
"""

SIM_PIN = None
"""
Optional: Set this only if your SIM card requires a PIN for activation. 
Most IoT SIMs do not need this.
"""

SERVER_ADDRESS = 'walterdemo.quickspot.io'
"""
The address of the Walter Demo server.
"""

SERVER_PORT = 1999
"""
The UDP port of the Walter Demo server.
"""