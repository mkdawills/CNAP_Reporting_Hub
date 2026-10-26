# Backup and restore

The database holds everything except uploaded files; uploaded files live in the `media` volume (`MEDIA_ROOT`).

## Nightly backup

```bash
make backup                    # writes backups/<timestamp>.sql.gz
```

Schedule it with cron on the host, and copy `backups/` plus the media volume to approved storage off the host. Keep at least 30 daily copies.

## Restore

```bash
make down
docker volume rm cnap-platform_pgdata     # only when replacing the whole database
make up
make restore FILE=backups/<timestamp>.sql.gz
```

Then restore the media volume from its copy.

## Rehearse

Restore to a scratch machine once per reporting period and open the admin. A backup that has never been restored is not a backup. Record the date of each rehearsal here:

| Date | Restored by | Result |
| --- | --- | --- |
