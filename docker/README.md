# ⚠️ Superseded — legacy single-container docker setup

This branch (`backup/docker-single-container-legacy`) is a preserved snapshot of
HUF's original single-container Docker quick-try environment
(`docker-compose.yml` + `init.sh`), kept for historical reference and rollback
purposes only.

**This setup is superseded.** The current, recommended Docker environment is
the "fasterdocker" multi-service compose stack on the `develop` branch (see
`docker/README.md` there), which offers a prebuilt pull-and-run demo image,
faster boot times via physical MariaDB snapshots, and rotated (non-default)
credentials on first boot. Do not use this branch for new setups — it is
retained only so the original approach remains inspectable.
