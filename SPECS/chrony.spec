%global package_speccommit c2a187e57c9437270608fbb41ef05c0d9aeb6681
%global usver 4.1
%global xsver 1
%global xsrel %{xsver}%{?xscount}%{?xshash}

%global _hardened_build 1
%global clknetsim_ver 64df92c5
%bcond_without debug
%bcond_without nts

Name:           chrony
Version:        4.1
Release: %{?xsrel}%{?dist}
Summary:        An NTP client/server

License:        GPLv2
URL:            https://chrony.tuxfamily.org
Source0: chrony-4.1.tar.gz
Source3: chrony.dhclient
Patch0: chrony-nm-dispatcher-dhcp.patch
# simulator for test suite
Source10: clknetsim-64df92c5.tar.gz

# add Fedora/RHEL-specific bits to DHCP dispatcher, including
# deferring to dhclient if installled, and using /etc/sysconfig

BuildRequires:  libcap-devel libedit-devel nettle-devel
%ifarch %{ix86} x86_64 %{arm} aarch64 mipsel mips64el ppc64 ppc64le s390 s390x
BuildRequires:  libseccomp-devel
%endif
BuildRequires:  gcc gcc-c++ make bison systemd gnupg2 net-tools
%{?with_nts:BuildRequires: gnutls-devel gnutls-utils}

Requires(pre):  shadow-utils
%{?systemd_requires}

# Old NetworkManager expects the dispatcher scripts in a different place
Conflicts:      NetworkManager < 1.20


%description
chrony is a versatile implementation of the Network Time Protocol (NTP).
It can synchronise the system clock with NTP servers, reference clocks
(e.g. GPS receiver), and manual input using wristwatch and keyboard. It
can also operate as an NTPv4 (RFC 5905) server and peer to provide a time
service to other computers in the network.

# XenServer has xenserver.pool.ntp.org vendorzone
%global vendorzone xenserver.

%prep
%autosetup -p1 -n %{name}-%{version}%{?prerelease} -a 10

%{?gitpatch: echo %{version}-%{gitpatch} > version.txt}

# review changes in packaged configuration files and scripts
md5sum -c <<-EOF | (! grep -v 'OK$')
        bc563c1bcf67b2da774bd8c2aef55a06  examples/chrony-wait.service
        2d01b94bc1a7b7fb70cbee831488d121  examples/chrony.conf.example2
        96999221eeef476bd49fe97b97503126  examples/chrony.keys.example
        6a3178c4670de7de393d9365e2793740  examples/chrony.logrotate
        a7054c9352c07384bd7ea0477e6e8a8c  examples/chrony.nm-dispatcher.dhcp
        8f5a98fcb400a482d355b929d04b5518  examples/chrony.nm-dispatcher.onoffline
        32c34c995c59fd1c3ad1616d063ae4a0  examples/chronyd.service
EOF

# don't allow packaging without vendor zone
test -n "%{vendorzone}"

# use example chrony.conf as the default config with some modifications:
# - use our vendor zone and replace the pool directive with server
# directives as xenrt/xsconsole/host-installer detect server directive
# - enable leapseclist to get TAI-UTC offset and leap seconds
# - use NTP servers from DHCP
sed -e 's|^\(pool \)\(pool.ntp.org.*\)|'\
'server 0.%{vendorzone}\2\nserver 1.%{vendorzone}\2\n'\
'server 2.%{vendorzone}\2\nserver 3.%{vendorzone}\2|' \
-e 's|#\(leapseclist\)|\1|' \
-e 's|^server.*pool.ntp.org.*|&\n\n# Use NTP servers from DHCP.\nsourcedir /run/chrony-dhcp|' \
        < examples/chrony.conf.example2 > chrony.conf

touch -r examples/chrony.conf.example2 chrony.conf

# regenerate the file from getdate.y
rm -f getdate.c

mv clknetsim-%{clknetsim_ver}* test/simulation/clknetsim

%build
%configure \
%{?with_debug: --enable-debug} \
        --enable-ntp-signd \
        --enable-scfilter \
%{!?with_nts: --disable-nts} \
        --chronyrundir=/run/chrony \
        --docdir=%{_docdir} \
        --with-ntp-era=$(date -d '1970-01-01 00:00:00+00:00' +'%s') \
        --with-user=chrony \
        --with-hwclockfile=%{_sysconfdir}/adjtime \
        --with-pidfile=/run/chrony/chronyd.pid \
        --with-sendmail=%{_sbindir}/sendmail
%make_build CFLAGS="-DO_TMPFILE=0x00800000 -fPIC" -C test/simulation/clknetsim

%install
%make_install

rm -rf $RPM_BUILD_ROOT%{_docdir}

mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/{sysconfig,logrotate.d}
mkdir -p $RPM_BUILD_ROOT%{_localstatedir}/{lib,log}/chrony
mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/dhcp/dhclient.d
mkdir -p $RPM_BUILD_ROOT%{_libexecdir}
mkdir -p $RPM_BUILD_ROOT%{_prefix}/lib/NetworkManager/dispatcher.d
mkdir -p $RPM_BUILD_ROOT{%{_unitdir},%{_prefix}/lib/systemd/ntp-units.d}

install -m 644 -p chrony.conf $RPM_BUILD_ROOT%{_sysconfdir}/chrony.conf

install -m 640 -p examples/chrony.keys.example \
        $RPM_BUILD_ROOT%{_sysconfdir}/chrony.keys
install -m 755 -p %{SOURCE3} \
        $RPM_BUILD_ROOT%{_sysconfdir}/dhcp/dhclient.d/chrony.sh
install -m 644 -p examples/chrony.logrotate \
        $RPM_BUILD_ROOT%{_sysconfdir}/logrotate.d/chrony

install -m 644 -p examples/chronyd.service \
        $RPM_BUILD_ROOT%{_unitdir}/chronyd.service
install -m 755 -p examples/chrony.nm-dispatcher.onoffline \
        $RPM_BUILD_ROOT%{_prefix}/lib/NetworkManager/dispatcher.d/20-chrony-onoffline
install -m 755 -p examples/chrony.nm-dispatcher.dhcp \
        $RPM_BUILD_ROOT%{_prefix}/lib/NetworkManager/dispatcher.d/20-chrony-dhcp
install -m 644 -p examples/chrony-wait.service \
        $RPM_BUILD_ROOT%{_unitdir}/chrony-wait.service

cat > $RPM_BUILD_ROOT%{_sysconfdir}/sysconfig/chronyd <<EOF
# Command-line options for chronyd
OPTIONS=""
EOF

touch $RPM_BUILD_ROOT%{_localstatedir}/lib/chrony/{drift,rtc}

echo 'chronyd.service' > \
        $RPM_BUILD_ROOT%{_prefix}/lib/systemd/ntp-units.d/50-chronyd.list

%check
# set random seed to get deterministic results
export CLKNETSIM_RANDOM_SEED=24505
%make_build -C test/simulation/clknetsim
make quickcheck

%pre
getent group chrony > /dev/null || /usr/sbin/groupadd -r chrony
getent passwd chrony > /dev/null || /usr/sbin/useradd -r -g chrony \
       -d %{_localstatedir}/lib/chrony -s /sbin/nologin chrony
# Save chrony.sh permissions before upgrade to preserve NTP mode setting
if [ $1 -gt 1 ] && [ -f %{_sysconfdir}/dhcp/dhclient.d/chrony.sh ]; then
        stat -c '%a' %{_sysconfdir}/dhcp/dhclient.d/chrony.sh > /var/tmp/chrony.sh.perms 2>/dev/null || :
fi
:

%post
# workaround for late reload of unit file (#1614751)
%{_bindir}/systemctl daemon-reload
# Restore chrony.sh permissions to preserve NTP mode setting
if [ -f /var/tmp/chrony.sh.perms ]; then
        chmod $(cat /var/tmp/chrony.sh.perms) %{_sysconfdir}/dhcp/dhclient.d/chrony.sh 2>/dev/null || :
        rm -f /var/tmp/chrony.sh.perms
fi
# migrate from chrony-helper to sourcedir directive
if test -a %{_libexecdir}/chrony-helper; then
        grep -qi 'sourcedir /run/chrony-dhcp$' %{_sysconfdir}/chrony.conf 2> /dev/null || \
                echo -e '\n# Use NTP servers from DHCP.\nsourcedir /run/chrony-dhcp' >> \
                        %{_sysconfdir}/chrony.conf
        mkdir -p /run/chrony-dhcp
        for f in %{_localstatedir}/lib/dhclient/chrony.servers.*; do
                sed 's|.*|server &|' < $f > /run/chrony-dhcp/"${f##*servers.}.sources"
        done 2> /dev/null
fi
%systemd_post chronyd.service chrony-wait.service

%preun
%systemd_preun chronyd.service chrony-wait.service

%postun
%systemd_postun_with_restart chronyd.service

%files
%{!?_licensedir:%global license %%doc}
%license COPYING
%doc FAQ NEWS README
%config(noreplace) %{_sysconfdir}/chrony.conf
%config(noreplace) %verify(not md5 size mtime) %attr(640,root,chrony) %{_sysconfdir}/chrony.keys
%config(noreplace) %{_sysconfdir}/logrotate.d/chrony
%config(noreplace) %{_sysconfdir}/sysconfig/chronyd
%{_sysconfdir}/dhcp/dhclient.d/chrony.sh
%{_bindir}/chronyc
%{_sbindir}/chronyd
%{_prefix}/lib/NetworkManager
%{_prefix}/lib/systemd/ntp-units.d/*.list
%{_unitdir}/chrony*.service
%{_mandir}/man[158]/%{name}*.[158]*
%dir %attr(750,chrony,chrony) %{_localstatedir}/lib/chrony
%ghost %attr(-,chrony,chrony) %{_localstatedir}/lib/chrony/drift
%ghost %attr(-,chrony,chrony) %{_localstatedir}/lib/chrony/rtc
%dir %attr(750,chrony,chrony) %{_localstatedir}/log/chrony

%changelog
* Sun Sep 28 2025 Lin Liu <Lin.Liu01@cloud.com> - 4.1-1
- CP-309761: Update to 4.1
- CA-417541: Update pool directive to server directive

* Fri Sep 19 2025 Lin Liu <Lin.Liu01@cloud.com> - 3.2-3
- CA-416786: Use correct ntp.org vendorzone

* Wed Sep 17 2025 Lin Liu <Lin.Liu01@cloud.com> - 3.2-2
- First imported release

