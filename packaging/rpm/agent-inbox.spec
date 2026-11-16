Name:           agent-inbox
Version:        0.4.0
Release:        2%{?dist}
Summary:        One inbox for your coding agents
License:        MIT
URL:            https://github.com/vp916/agent-inbox
Source0:        %{url}/archive/refs/tags/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-pyside6
Requires:       layer-shell-qt
Requires:       qt6-qtdeclarative
Requires:       qt6-qtwayland
Requires:       systemd
Recommends:     pipewire-utils
Recommends:     sound-theme-freedesktop

%description
An overlay that shows what Claude Code, Codex, Copilot, Antigravity, OpenCode and
other coding agents are doing, and lets you answer their questions and permission
prompts without switching windows. Needs a Wayland desktop with layer-shell
(KDE Plasma 6, Hyprland, Sway, niri).

Run 'agent-inbox-setup install' as your user after installing.

%prep
%autosetup

%build

%install
install -d %{buildroot}%{_datadir}/%{name} %{buildroot}%{_bindir}
cp -r bin daemon hook ui install.py %{buildroot}%{_datadir}/%{name}/
ln -s %{_datadir}/%{name}/bin/agent-inbox %{buildroot}%{_bindir}/agent-inbox
ln -s %{_datadir}/%{name}/install.py %{buildroot}%{_bindir}/agent-inbox-setup

%post
echo "Run 'agent-inbox-setup install' as your user to add the agent hooks and start the services."

%preun
if [ "$1" = 0 ]; then
  echo "Hooks and user services are per user: run 'agent-inbox-setup uninstall' as your user as well."
fi

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_datadir}/%{name}
%{_bindir}/agent-inbox
%{_bindir}/agent-inbox-setup

%changelog
* Mon Nov 16 2026 vp916 - 0.4.0-2
- Built by COPR from the release branch; README updates only

* Mon Nov 16 2026 vp916 - 0.4.0-1
- OpenCode support, overlay on the active screen, Codex stop fix
