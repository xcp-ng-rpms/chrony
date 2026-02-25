%global _hardened_build 1
%global clknetsim_ver 71dbbc
%bcond_without debug

Name:           chrony
Version:        3.2
Release:        2%{?dist}
Summary:        An NTP client/server

Group:          System Environment/Daemons
License:        GPLv2
URL:            https://chrony.tuxfamily.org
Source0:        https://download.tuxfamily.org/chrony/chrony-%{version}%{?prerelease}.tar.gz
Source1:        chrony.dhclient
Source2:        chrony.helper
Source3:        chrony-dnssrv@.service
Source4:        chrony-dnssrv@.timer
# simulator for test suite
Source10:       https://github.com/mlichvar/clknetsim/archive/%{clknetsim_ver}/clknetsim-%{clknetsim_ver}.tar.gz

# add NTP servers from DHCP when starting service
Patch1:         chrony-service-helper.patch
# enable support for SW/HW timestamping on older kernels
Patch2:         chrony-timestamping.patch
# revert upstream changes in packaged chrony.conf example
Patch3:         chrony-defconfig.patch
# fix chronyc getting stuck in infinite loop after clock step
Patch4:         chrony-select-timeout.patch

BuildRequires:  libcap-devel libedit-devel nss-devel pps-tools-devel
%ifarch %{ix86} x86_64 %{arm} aarch64 ppc64 ppc64le s390 s390x
BuildRequires:  libseccomp-devel
%endif
BuildRequires:  bison systemd-units

Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd

%description
A client/server for the Network Time Protocol, this program keeps your
computer's clock accurate. It was specially designed to support
systems with intermittent internet connections, but it also works well
in permanently connected environments. It can use also hardware reference
clocks, system real-time clock or manual input as time references.

%if 0%{!?vendorzone:1}
%global vendorzone %(source /etc/os-release && echo ${ID}.)
%endif

%prep
%setup -q -n %{name}-%{version}%{?prerelease} -a 10
%patch1 -p1 -b .service-helper
%patch2 -p1 -b .timestamping
%patch3 -p1 -b .defconfig
%patch4 -p1 -b .select-timeout

# review changes in packaged configuration files and scripts
md5sum -c <<-EOF | (! grep -v 'OK$')
        47ad7eccc410b981d2f2101cf5682616  examples/chrony-wait.service
        58978d335ec3752ac2c38fa82b48f0a5  examples/chrony.conf.example2
        ba6bb05c50e03f6b5ab54a2b7914800d  examples/chrony.keys.example
        6a3178c4670de7de393d9365e2793740  examples/chrony.logrotate
        27cbc940c94575de320dbd251cbb4514  examples/chrony.nm-dispatcher
        a85246982a89910b1e2d3356b7d131d7  examples/chronyd.service
EOF

# don't allow empty vendor zone
test -n "%{vendorzone}"

# use our vendor zone and replace the pool directive with server
# directives as some configuration tools don't support it yet
sed -e 's|^\(pool \)\(pool.ntp.org.*\)|'\
'server 0.%{vendorzone}\2\nserver 1.%{vendorzone}\2\n'\
'server 2.%{vendorzone}\2\nserver 3.%{vendorzone}\2|' \
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
        --docdir=%{_docdir} \
        --with-ntp-era=$(date -d '1970-01-01 00:00:00+00:00' +'%s') \
        --with-user=chrony \
        --with-hwclockfile=%{_sysconfdir}/adjtime \
        --with-sendmail=%{_sbindir}/sendmail
make %{?_smp_mflags}

%install
make install DESTDIR=$RPM_BUILD_ROOT

rm -rf $RPM_BUILD_ROOT%{_docdir}

mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/{sysconfig,logrotate.d}
mkdir -p $RPM_BUILD_ROOT%{_localstatedir}/{lib,log}/chrony
mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/NetworkManager/dispatcher.d
mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/dhcp/dhclient.d
mkdir -p $RPM_BUILD_ROOT%{_libexecdir}
mkdir -p $RPM_BUILD_ROOT{%{_unitdir},%{_prefix}/lib/systemd/ntp-units.d}

install -m 644 -p chrony.conf $RPM_BUILD_ROOT%{_sysconfdir}/chrony.conf

install -m 640 -p examples/chrony.keys.example \
        $RPM_BUILD_ROOT%{_sysconfdir}/chrony.keys
install -m 755 -p examples/chrony.nm-dispatcher \
        $RPM_BUILD_ROOT%{_sysconfdir}/NetworkManager/dispatcher.d/20-chrony
install -m 755 -p %{SOURCE1} \
        $RPM_BUILD_ROOT%{_sysconfdir}/dhcp/dhclient.d/chrony.sh
install -m 644 -p examples/chrony.logrotate \
        $RPM_BUILD_ROOT%{_sysconfdir}/logrotate.d/chrony

install -m 644 -p examples/chronyd.service \
        $RPM_BUILD_ROOT%{_unitdir}/chronyd.service
install -m 644 -p examples/chrony-wait.service \
        $RPM_BUILD_ROOT%{_unitdir}/chrony-wait.service
install -m 644 -p %{SOURCE3} $RPM_BUILD_ROOT%{_unitdir}/chrony-dnssrv@.service
install -m 644 -p %{SOURCE4} $RPM_BUILD_ROOT%{_unitdir}/chrony-dnssrv@.timer

install -m 755 -p %{SOURCE2} $RPM_BUILD_ROOT%{_libexecdir}/chrony-helper

cat > $RPM_BUILD_ROOT%{_sysconfdir}/sysconfig/chronyd <<EOF
# Command-line options for chronyd
OPTIONS=""
EOF

touch $RPM_BUILD_ROOT%{_localstatedir}/lib/chrony/{drift,rtc}

echo 'chronyd.service' > \
        $RPM_BUILD_ROOT%{_prefix}/lib/systemd/ntp-units.d/50-chronyd.list

%check
# set random seed to get deterministic results
export CLKNETSIM_RANDOM_SEED=24502
make %{?_smp_mflags} -C test/simulation/clknetsim
make quickcheck

%pre
getent group chrony > /dev/null || /usr/sbin/groupadd -r chrony
getent passwd chrony > /dev/null || /usr/sbin/useradd -r -g chrony \
       -d %{_localstatedir}/lib/chrony -s /sbin/nologin chrony
:

%post
%systemd_post chronyd.service chrony-wait.service

%preun
%systemd_preun chronyd.service chrony-wait.service

%postun
%systemd_postun_with_restart chronyd.service

%files
%doc COPYING FAQ NEWS README
%config(noreplace) %{_sysconfdir}/chrony.conf
%config(noreplace) %verify(not md5 size mtime) %attr(640,root,chrony) %{_sysconfdir}/chrony.keys
%config(noreplace) %{_sysconfdir}/logrotate.d/chrony
%config(noreplace) %{_sysconfdir}/sysconfig/chronyd
%{_sysconfdir}/NetworkManager/dispatcher.d/20-chrony
%{_sysconfdir}/dhcp/dhclient.d/chrony.sh
%{_bindir}/chronyc
%{_sbindir}/chronyd
%{_libexecdir}/chrony-helper
%{_prefix}/lib/systemd/ntp-units.d/*.list
%{_unitdir}/chrony*.service
%{_unitdir}/chrony*.timer
%{_mandir}/man[158]/%{name}*.[158]*
%dir %attr(-,chrony,chrony) %{_localstatedir}/lib/chrony
%ghost %attr(-,chrony,chrony) %{_localstatedir}/lib/chrony/drift
%ghost %attr(-,chrony,chrony) %{_localstatedir}/lib/chrony/rtc
%dir %attr(-,chrony,chrony) %{_localstatedir}/log/chrony

%changelog
* Tue Dec 05 2017 Miroslav Lichvar <mlichvar@redhat.com> 3.2-2
- fix chronyc getting stuck in infinite loop after clock step (#1520884)

* Tue Sep 19 2017 Miroslav Lichvar <mlichvar@redhat.com> 3.2-1
- update to 3.2 (#1482565 #1462081 #1454765)
- use ID from /etc/os-release to set pool.ntp.org vendor zone

* Mon Apr 24 2017 Miroslav Lichvar <mlichvar@redhat.com> 3.1-2
- don't drop PHC samples with zero delay (#1443342)

* Fri Feb 03 2017 Miroslav Lichvar <mlichvar@redhat.com> 3.1-1
- update to 3.1 (#1387223 #1274250 #1350669 #1406445)
- don't start chronyd without capability to set system clock (#1306046)
- fix chrony-helper to escape names of systemd units (#1418968)
- package chronyd sysconfig file (#1396840)

* Fri Nov 18 2016 Miroslav Lichvar <mlichvar@redhat.com> 2.1.1-4
- fix crash with smoothtime leaponly directive (#1392793)

* Tue Jun 28 2016 Miroslav Lichvar <mlichvar@redhat.com> 2.1.1-3
- fix chrony-helper to exit with correct status (#1350531)

* Wed May 25 2016 Miroslav Lichvar <mlichvar@redhat.com> 2.1.1-2
- extend chrony-helper to allow management of static sources (#1331655)

* Tue Jun 23 2015 Miroslav Lichvar <mlichvar@redhat.com> 2.1.1-1
- update to 2.1.1 (#1117882)
- add -n option to gzip command to not save timestamp

* Mon Jun 22 2015 Miroslav Lichvar <mlichvar@redhat.com> 2.1-1
- update to 2.1 (#1117882 #1169353 #1206504 #1209568 CVE-2015-1821
  CVE-2015-1822 CVE-2015-1853)
- extend chrony-helper to allow using servers from DNS SRV records (#1211600)
- add servers from DHCP with iburst option by default (#1219492)
- execute test suite

* Tue Feb 04 2014 Miroslav Lichvar <mlichvar@redhat.com> 1.29.1-1
- update to 1.29.1 (#1053022, CVE-2014-0021)
- fix selecting of sources with prefer option (#1061048)
- fix potential bug in writing of drift files (#1061106)
- replace hardening build flags with _hardened_build (#1061036)

* Fri Jan 24 2014 Daniel Mach <dmach@redhat.com> - 1.29-4
- Mass rebuild 2014-01-24

* Fri Dec 27 2013 Daniel Mach <dmach@redhat.com> - 1.29-3
- Mass rebuild 2013-12-27

* Thu Oct 03 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.29-2
- add ordering dependency to not start chronyd before ntpd stopped (#1011968)

* Fri Aug 09 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.29-1
- update to 1.29 (#995373, CVE-2012-4502, CVE-2012-4503)

* Wed Jul 17 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.28-1
- update to 1.28
- change default makestep limit to 10 seconds

* Mon Jun 24 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.28-0.2.pre1
- buildrequire systemd-units

* Fri Jun 21 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.28-0.1.pre1
- update to 1.28-pre1
- listen for commands only on localhost by default

* Thu May 09 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.27-3
- disable chrony-wait service by default (#961047)
- drop old systemd scriptlets
- don't own ntp-units.d directory
- move files from /lib
- remove unncessary dependency on syslog target

* Tue Mar 12 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.27-2
- suppress error messages from tr when generating key (#907914)
- fix delta calculation with extreme frequency offsets

* Fri Feb 01 2013 Miroslav Lichvar <mlichvar@redhat.com> 1.27-1
- update to 1.27
- start chrony-wait service with chronyd
- start chronyd service after sntp
- remove obsolete macros

* Tue Sep 11 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.27-0.5.pre1.git1ca844
- update to git snapshot 1ca844
- update systemd integration (#846303)
- use systemd macros if available (#850151)
- use correct vendor pool.ntp.org zone on RHEL (#845981)
- don't log output of chrony-wait service

* Wed Jul 18 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 1.27-0.4.pre1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_18_Mass_Rebuild

* Fri Apr 27 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.27-0.3.pre1
- update service file for systemd-timedated-ntp target (#816493)

* Fri Apr 06 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.27-0.2.pre1
  use systemctl is-active instead of status in chrony-helper (#794771)

* Tue Feb 28 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.27-0.1.pre1
- update to 1.27-pre1
- generate SHA1 command key instead of MD5

* Wed Feb 15 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.26-6.20110831gitb088b7
- remove old servers on DHCP update (#787042)

* Fri Feb 10 2012 Miroslav Lichvar <mlichvar@redhat.com> 1.26-5.20110831gitb088b7
- improve chrony-helper to keep track of servers added from DHCP (#787042)
- fix dhclient script to always return with zero exit code (#767859)

* Thu Jan 12 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 1.26-4.20110831gitb088b7
- Rebuilt for https://fedoraproject.org/wiki/Fedora_17_Mass_Rebuild

* Tue Sep 06 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.26-3.20110831gitb088b7
- update to git snapshot 20110831gitb088b7
- on first start generate password with 16 chars
- change systemd service type to forking
- add forced-command to chrony-helper (#735821)

* Mon Aug 15 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.26-2
- fix iburst with very high jitters and long delays
- use timepps header from pps-tools-devel

* Wed Jul 13 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.26-1
- update to 1.26
- read options from sysconfig file if it exists

* Fri Jun 24 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.26-0.1.pre1
- update to 1.26-pre1
- fix service name in %%triggerun
- drop SysV init script
- add chrony-wait service

* Fri May 06 2011 Bill Nottingham <notting@redhat.com> 1.25-2
- fix systemd scriptlets for the upgrade case

* Wed May 04 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.25-1
- update to 1.25

* Wed Apr 20 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.25-0.3.pre2
- update to 1.25-pre2
- link with -Wl,-z,relro,-z,now options

* Tue Feb 08 2011 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 1.25-0.2.pre1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_15_Mass_Rebuild

* Tue Feb 01 2011 Miroslav Lichvar <mlichvar@redhat.com> 1.25-0.1.pre1
- update to 1.25-pre1
- use iburst, four pool servers, rtcsync, stratumweight in default config
- add systemd support
- drop sysconfig file 
- suppress install-info errors

* Thu Apr 29 2010 Miroslav Lichvar <mlichvar@redhat.com> 1.24-4.20100428git73d775
- update to 20100428git73d775
- replace initstepslew directive with makestep in default config
- add NetworkManager dispatcher script
- add dhclient script
- retry server/peer name resolution at least once to workaround
  NetworkManager race condition on boot
- don't verify chrony.keys

* Fri Mar 12 2010 Miroslav Lichvar <mlichvar@redhat.com> 1.24-3.20100302git5fb555
- update to snapshot 20100302git5fb555
- compile with PPS API support

* Thu Feb 04 2010 Miroslav Lichvar <mlichvar@redhat.com> 1.24-1
- update to 1.24 (#555367, CVE-2010-0292 CVE-2010-0293 CVE-2010-0294)
- modify default config
  - step clock on start if it is off by more than 100 seconds
  - disable client log
- build with -fPIE on sparc

* Tue Dec 15 2009 Miroslav Lichvar <mlichvar@redhat.com> 1.24-0.1.pre1
- update to 1.24-pre1

* Fri Jul 24 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 1.23-7.20081106gitbe42b4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_12_Mass_Rebuild

* Fri Jul 17 2009 Miroslav Lichvar <mlichvar@redhat.com> 1.23-6.20081106gitbe42b4
- switch to editline
- support arbitrary chronyc commands in init script

* Mon Jun 08 2009 Dan Horak <dan[at]danny.cz> 1.23-5.20081106gitbe42b4
- add patch with support for s390/s390x

* Mon Mar 09 2009 Miroslav Lichvar <mlichvar@redhat.com> 1.23-4.20081106gitbe42b4
- fix building with broken libcap header (#483548)

* Mon Feb 23 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 1.23-3.20081106gitbe42b4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_11_Mass_Rebuild

* Wed Nov 19 2008 Miroslav Lichvar <mlichvar@redhat.com> 1.23-2.20081106gitbe42b4
- fix info uninstall
- generate random command key in init script
- support cyclelogs, online, offline commands in init script
- add logrotate script

* Tue Nov 11 2008 Miroslav Lichvar <mlichvar@redhat.com> 1.23-1.20081106gitbe42b4
- initial release
