# COPR (vp916/agent-inbox) builds the source RPM with this: SCM package, "make srpm" method.
# It watches the `release` branch, so a release is: tag vX.Y.Z, then `git push origin main:release`.
# COPR runs `make -f .copr/Makefile srpm outdir=... spec=...` as root inside the clone.
spec ?= packaging/rpm/agent-inbox.spec

srpm:
	dnf -y install git-core rpm-build
	V=$$(sed -n 's/^Version: *//p' $(spec)); \
	git -c safe.directory='*' archive --format=tar.gz --prefix=agent-inbox-$$V/ -o $(outdir)/agent-inbox-$$V.tar.gz HEAD
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" $(spec)
