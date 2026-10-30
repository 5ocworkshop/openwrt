# <FILE>contrib/ac86u/Makefile</FILE> - <DESC>Portable guarded AC86U native OpenWrt build entrypoints.</DESC>
# <VERS>VERSION: 0.2.0</VERS>
# <WCTX>Reuse native OpenWrt caches with explicit single-device and provenance checks.</WCTX>
# <CLOG>Find profiles in image/Makefile and existing .mk fragments without unmatched-glob errors.</CLOG>
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
ENV_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
OPENWRT_ROOT ?= $(abspath $(ENV_DIR)/../..)
JOBS ?= 1
VARIANT ?= RC1-public
BANNER_LABEL ?= ASUS RT-AC86U 25.12.6 RC1-public
BUILD_ID ?=
DEFAULT_RUN_DIR := $(OPENWRT_ROOT)/.port/runs/$(shell date -u +%Y%m%dT%H%M%S%NZ)
RUN_DIR ?= $(DEFAULT_RUN_DIR)
LINUX_PATH ?= /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH := $(LINUX_PATH)
NATIVE_MAKE := make
RUNNER := $(ENV_DIR)/scripts/cls_run_stage.py
STAMPER := $(ENV_DIR)/scripts/fnc_stamp_build_identity.py
PROFILE := CONFIG_TARGET_bcm4908_generic_DEVICE_asus_rt-ac86u=y

.PHONY: help check-profile configure check-config firmware test
help:
	@printf '%s\n' 'Use make -f contrib/ac86u/Makefile TARGET [KEY=value]' 'configure: seed a new .config; firmware: stamp and build; test: focused CLI tests' 'OPENWRT_ROOT=source JOBS=1 RUN_DIR=new-path BUILD_ID=optional VARIANT=RC1-public' 'BANNER_LABEL=display-text LINUX_PATH=Linux-only-path' 'Run builds and tests inside the required site compute admission.'

check-profile:
	@shopt -s nullglob; profiles=("$(OPENWRT_ROOT)"/target/linux/bcm4908/image/*.mk); \
	if [[ -f "$(OPENWRT_ROOT)/target/linux/bcm4908/image/Makefile" ]]; then profiles+=("$(OPENWRT_ROOT)/target/linux/bcm4908/image/Makefile"); fi; \
	if (( $${#profiles[@]} == 0 )) || ! grep -q -E '^define Device/asus_rt-ac86u[[:space:]]*$$' "$${profiles[@]}"; then \
		echo 'Missing ASUS RT-AC86U profile: review/apply board-support patches first.' >&2; exit 2; \
	fi

configure: check-profile
	@test ! -e "$(OPENWRT_ROOT)/.config" || { echo 'Existing .config preserved; reconcile explicitly.' >&2; exit 2; }
	@cp -n "$(ENV_DIR)/config.seed" "$(OPENWRT_ROOT)/.config"
	@python3 "$(RUNNER)" --run-dir "$(RUN_DIR)/configure" --cwd "$(OPENWRT_ROOT)" --label configure -- env PATH="$(LINUX_PATH)" $(NATIVE_MAKE) defconfig
	@$(MAKE) --no-print-directory -f "$(ENV_DIR)/Makefile" check-config OPENWRT_ROOT="$(OPENWRT_ROOT)"

check-config: check-profile
	@grep -q -x '$(PROFILE)' "$(OPENWRT_ROOT)/.config" || { echo 'AC86U single-device profile is not selected.' >&2; exit 2; }
	@! grep -q -E '^CONFIG_TARGET_(MULTI_PROFILE|ALL_PROFILES)=y$$' "$(OPENWRT_ROOT)/.config" || { echo 'Multiple/all device profiles are refused.' >&2; exit 2; }
	@test "$$(grep -c -E '^CONFIG_TARGET_bcm4908_generic_DEVICE_.*=y$$' "$(OPENWRT_ROOT)/.config")" = 1 || { echo 'Expected exactly one AC86U device.' >&2; exit 2; }

firmware: check-config
	@[[ "$(JOBS)" =~ ^[1-9][0-9]*$$ ]] || { echo 'JOBS must be a positive integer.' >&2; exit 2; }
	@python3 "$(STAMPER)" --openwrt-root "$(OPENWRT_ROOT)" --run-dir "$(RUN_DIR)/identity" --variant "$(VARIANT)" --banner-label "$(BANNER_LABEL)" --manufacturer ASUS --product RT-AC86U $(if $(BUILD_ID),--build-id "$(BUILD_ID)")
	@python3 "$(RUNNER)" --run-dir "$(RUN_DIR)/defconfig" --cwd "$(OPENWRT_ROOT)" --label firmware-defconfig -- env PATH="$(LINUX_PATH)" $(NATIVE_MAKE) defconfig
	@$(MAKE) --no-print-directory -f "$(ENV_DIR)/Makefile" check-config OPENWRT_ROOT="$(OPENWRT_ROOT)"
	@python3 "$(RUNNER)" --run-dir "$(RUN_DIR)/build" --cwd "$(OPENWRT_ROOT)" --label firmware-build -- env PATH="$(LINUX_PATH)" $(NATIVE_MAKE) -j"$(JOBS)"

test:
	@python3 -m unittest discover -s "$(ENV_DIR)/tests" -p 'test_*.py'
# <FILE>contrib/ac86u/Makefile</FILE> - <DESC>Portable guarded AC86U native OpenWrt build entrypoints.</DESC>
# <VERS>END OF VERSION: 0.2.0</VERS>
