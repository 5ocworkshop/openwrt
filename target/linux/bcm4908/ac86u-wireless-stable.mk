# <FILE>target/linux/bcm4908/ac86u-wireless-stable.mk</FILE> - <DESC>Explicit AC86U stable wireless image selection.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Enable ordered native module loading for the selected hardware-tested AC86U profile.</WCTX>
# <CLOG>Apply stable radio package policy only when the RT-AC86U device is selected.</CLOG>
AC86U_WIRELESS_STABLE:=$(if $(CONFIG_TARGET_bcm4908_generic_DEVICE_asus_rt-ac86u),1)
# <FILE>target/linux/bcm4908/ac86u-wireless-stable.mk</FILE> - <DESC>Explicit AC86U stable wireless image selection.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
