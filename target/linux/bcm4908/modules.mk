# <FILE>target/linux/bcm4908/modules.mk</FILE> - <DESC>Package the PCIe host with explicit stable-image loading policy.</DESC>
# <VERS>VERSION: 0.2.0</VERS>
# <WCTX>Load the tested AC86U host profile before wireless only in explicitly selected stable images.</WCTX>
# <CLOG>Add ordered native autoload and host-profile parameters while preserving parked default preparation.</CLOG>

-include $(TOPDIR)/target/linux/bcm4908/ac86u-wireless-stable.mk
PKG_FILE_DEPENDS += $(wildcard $(TOPDIR)/target/linux/bcm4908/ac86u-wireless-stable.mk)

define KernelPackage/bcm4908-pcie
  SUBMENU:=Other modules
  TITLE:=BCM4908 PCIe host
  DEPENDS:=@TARGET_bcm4908
  KCONFIG:= \
	CONFIG_PCI=y \
	CONFIG_PCI_MSI=y \
	CONFIG_RESET_CONTROLLER=y \
	CONFIG_RESET_SIMPLE=y \
	CONFIG_PCIE_BRCMSTB
  FILES:=$(LINUX_DIR)/drivers/pci/controller/pcie-brcmstb.ko
  AUTOLOAD:=$(if $(AC86U_WIRELESS_STABLE),$(call AutoLoad,40,pcie-brcmstb))
  MODPARAMS.pcie-brcmstb:=$(if $(AC86U_WIRELESS_STABLE),ac86u_merlin_host_compat=1)
endef

define KernelPackage/bcm4908-pcie/description
 Linux brcmstb PCIe host driver with a scoped RT-AC86U compatibility profile.
 Boot autoload is selected explicitly by the stable image integration.
endef

$(eval $(call KernelPackage,bcm4908-pcie))

# <FILE>target/linux/bcm4908/modules.mk</FILE> - <DESC>Package the PCIe host with explicit stable-image loading policy.</DESC>
# <VERS>END OF VERSION: 0.2.0</VERS>
