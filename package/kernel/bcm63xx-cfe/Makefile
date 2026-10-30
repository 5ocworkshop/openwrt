# <FILE>package/kernel/bcm63xx-cfe/Makefile</FILE> - <DESC>Stage published CFE payloads with a shared ASUS BCM4908 family path.</DESC>
# <VERS>VERSION: 0.1.0</VERS>
# <WCTX>Reuse the original published CFE bytes for ASUS BCM4908 image consumers.</WCTX>
# <CLOG>Relocate the GT-AC5300 payload to a physical shared path and retain its relative compatibility alias.</CLOG>
include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=bcm63xx-cfe
PKG_RELEASE:=2

PKG_SOURCE_URL:=https://github.com/openwrt/bcm63xx-cfe.git
PKG_SOURCE_PROTO:=git
PKG_SOURCE_DATE:=2025-04-02
PKG_SOURCE_VERSION:=b8128fa4bdcdaf97549138965b00d5d7ceb7bb0f
PKG_MIRROR_HASH:=d33fad4fb5f4419bb287f3c3df6cceabab01fc7852c24cf29a15befa38cc0d45

PKG_FLAGS:=nonshared

include $(INCLUDE_DIR)/package.mk

define Package/bcm63xx-cfe
  SECTION:=boot
  CATEGORY:=Boot Loaders
  DEPENDS:=@(TARGET_bcm4908||TARGET_bcm63xx||TARGET_bmips)
  TITLE:=bcm63xx-cfe
  DEFAULT:=y
endef

define Package/bcm63xx-cfe/description
  CFE RAM binaries for bcm63xx.
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	@test -f "$(PKG_BUILD_DIR)/asus,gt-ac5300/cferam.000" && test ! -L "$(PKG_BUILD_DIR)/asus,gt-ac5300/cferam.000" || { echo 'Missing regular GT-AC5300 CFE payload' >&2; exit 1; }
	mkdir -p "$(PKG_BUILD_DIR)/asus,bcm4908-family"
	mv "$(PKG_BUILD_DIR)/asus,gt-ac5300/cferam.000" "$(PKG_BUILD_DIR)/asus,bcm4908-family/cferam.000"
	ln -s ../asus,bcm4908-family/cferam.000 "$(PKG_BUILD_DIR)/asus,gt-ac5300/cferam.000"
endef

define Build/Compile
	true
endef

define Package/bcm63xx-cfe/install
	true
endef

define Build/InstallDev
	rm -rf $(STAGING_DIR_IMAGE)/$(PKG_NAME)
	mkdir -p $(STAGING_DIR_IMAGE)/$(PKG_NAME)
	$(CP) -r $(PKG_BUILD_DIR)/* $(STAGING_DIR_IMAGE)/$(PKG_NAME)
endef

$(eval $(call BuildPackage,bcm63xx-cfe))
# <FILE>package/kernel/bcm63xx-cfe/Makefile</FILE> - <DESC>Stage published CFE payloads with a shared ASUS BCM4908 family path.</DESC>
# <VERS>END OF VERSION: 0.1.0</VERS>
