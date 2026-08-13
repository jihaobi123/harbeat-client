# systemd adapter gate

Production units are intentionally not copied from the legacy environment.
New units will be generated only after each service has a production adapter.

Every accepted unit must:

- run as a dedicated `harbeat-<service>` user;
- execute from `/opt/harbeat/current`;
- load non-secret config from `/etc/harbeat/modules`;
- load secrets only from `/etc/harbeat/secrets`;
- write only to its own `/var/lib/harbeat/<service>` and log path;
- declare device and group access explicitly;
- pass the old-path scanner and real-device health check.
