# <FILE>target/linux/bcm4908/base-files.mk</FILE> - <DESC>Install AC86U factory-radio NVRAM RAM-target links through native base-files packaging.</DESC>
# <VERS>VERSION: 0.1.0</VERS>
# <WCTX>Keep per-unit calibration out of the ROM while retaining normal firmware file names.</WCTX>
# <CLOG>Add only the two AC86U-specific ROM symlinks when the exact native device profile is selected.</CLOG>

ifeq ($(CONFIG_TARGET_bcm4908_generic_DEVICE_asus_rt-ac86u),y)
define Package/base-files/install-target
	$(INSTALL_DIR) $(1)/lib/firmware/brcm
	$(LN) /tmp/ac86u-radio-nvram/brcmfmac4366c-pcie.asus,rt-ac86u-radio0.txt $(1)/lib/firmware/brcm/brcmfmac4366c-pcie.asus,rt-ac86u-radio0.txt
	$(LN) /tmp/ac86u-radio-nvram/brcmfmac4366c-pcie.asus,rt-ac86u-radio1.txt $(1)/lib/firmware/brcm/brcmfmac4366c-pcie.asus,rt-ac86u-radio1.txt
endef
endif

# <FILE>target/linux/bcm4908/base-files.mk</FILE> - <DESC>Install AC86U factory-radio NVRAM RAM-target links through native base-files packaging.</DESC>
# <VERS>END OF VERSION: 0.1.0</VERS>
