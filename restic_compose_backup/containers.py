import os
from pathlib import Path
from typing import List

from restic_compose_backup import utils

VOLUME_TYPE_BIND = "bind"
VOLUME_TYPE_VOLUME = "volume"


class Container:
    """Represents a docker container"""
    container_type = None

    def __init__(self, data: dict):
        self._data = data
        self._state = data.get('State')
        self._config = data.get('Config')
        self._mounts = [Mount(mnt, container=self) for mnt in data.get('Mounts')]

        if not self._state:
            raise ValueError('Container meta missing State')
        if self._config is None:
            raise ValueError('Container meta missing Config')

        self._labels = self._config.get('Labels')
        if self._labels is None:
            raise ValueError('Container meta missing Config->Labels')

        self._include = self._parse_pattern(self.get_label('restic-compose-backup.volumes.include'))
        self._exclude = self._parse_pattern(self.get_label('restic-compose-backup.volumes.exclude'))

    @property
    def instance(self) -> 'Container':
        """Container: Get a service specific subclass instance"""
        # TODO: Do this smarter in the future (simple registry)
        if self.database_backup_enabled:
            from restic_compose_backup import containers_db
            if self.mariadb_backup_enabled:
                return containers_db.MariadbContainer(self._data)
            if self.mysql_backup_enabled:
                return containers_db.MysqlContainer(self._data)
            if self.postgresql_backup_enabled:
                return containers_db.PostgresContainer(self._data)
        else:
            return self

    @property
    def id(self) -> str:
        """str: The id of the container"""
        return self._data.get('Id')

    @property
    def hostname(self) -> str:
        """12 character hostname based on id"""
        return self.id[:12]

    @property
    def image(self) -> str:
        """Image name"""
        return self.get_config('Image')

    @property
    def environment(self) -> list:
        """All configured env vars for the container as a list"""
        return self.get_config('Env', default=[])

    def get_config_env(self, name) -> str:
        """Get a config environment variable by name"""
        # convert to dict and fetch env var by name
        data = {i[0:i.find('=')]: i[i.find('=')+1:] for i in self.environment}
        return data.get(name)

    @property
    def volumes(self) -> dict:
        """
        Return volumes for the container in the following format:
            {'/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},}
        """
        volumes = {}
        for mount in self._mounts:
            volumes[mount.source] = {
                'bind': mount.destination,
                'mode': 'rw',
            }

        return volumes

    @property
    def backup_enabled(self) -> bool:
        """Is backup enabled for this container?"""
        return any([
            self.volume_backup_enabled,
            self.database_backup_enabled,
        ])

    @property
    def volume_backup_enabled(self) -> bool:
        return utils.is_true(self.get_label('restic-compose-backup.volumes'))

    @property
    def database_backup_enabled(self) -> bool:
        """bool: Is database backup enabled in any shape or form?"""
        return any([
            self.mysql_backup_enabled,
            self.mariadb_backup_enabled,
            self.postgresql_backup_enabled,
        ])

    @property
    def mysql_backup_enabled(self) -> bool:
        return utils.is_true(self.get_label('restic-compose-backup.mysql'))

    @property
    def mariadb_backup_enabled(self) -> bool:
        return utils.is_true(self.get_label('restic-compose-backup.mariadb'))

    @property
    def postgresql_backup_enabled(self) -> bool:
        return utils.is_true(self.get_label('restic-compose-backup.postgres'))

    @property
    def is_backup_process_container(self) -> bool:
        """Is this container the running backup process?"""
        return self.get_label('restic-compose-backup.backup_process') == 'True'

    @property
    def is_running(self) -> bool:
        """Is the container running?"""
        return self._state.get('Running', False)

    @property
    def name(self) -> str:
        """Container name"""
        return self._data['Name'].replace('/', '')

    @property
    def service_name(self) -> str:
        """Name of the container/service"""
        return self.get_label('com.docker.compose.service', default='')

    @property
    def project_name(self) -> str:
        """Name of the compose setup"""
        return self.get_label('com.docker.compose.project', default='')

    @property
    def is_oneoff(self) -> bool:
        """Was this container started with run command?"""
        return self.get_label('com.docker.compose.oneoff', default='False') == 'True'

    def get_config(self, name, default=None):
        """Get value from config dict"""
        return self._config.get(name, default)

    def get_label(self, name, default=None):
        """Get a label by name"""
        return self._labels.get(name, None)

    def filter_mounts(self):
        """Get all mounts for this container matching include/exclude filters"""
        filtered = []
        if self._include:
            for mount in self._mounts:
                for pattern in self._include:
                    if pattern in mount.source:
                        break
                else:
                    continue

                filtered.append(mount)

        elif self._exclude:
            for mount in self._mounts:
                for pattern in self._exclude:
                    if pattern in mount.source:
                        break
                else:
                    filtered.append(mount)
        else:
            return self._mounts

        return filtered

    def volumes_for_backup(self, source_prefix='/backup', mode='ro'):
        """Get volumes configured for backup"""
        mounts = self.filter_mounts()
        volumes = {}
        for mount in mounts:
            volumes[mount.source] = {
                'bind': str(Path(source_prefix) / self.service_name / Path(utils.strip_root(mount.destination))),
                'mode': mode,
            }

        return volumes

    def get_credentials(self) -> dict:
        """dict: get credentials for the service"""
        raise NotImplementedError("Base container class don't implement this")

    def ping(self) -> bool:
        """Check the availability of the service"""
        raise NotImplementedError("Base container class don't implement this")

    def backup(self):
        """Back up this service"""
        raise NotImplementedError("Base container class don't implement this")

    def dump_command(self) -> list:
        """list: create a dump command restic and use to send data through stdin"""
        raise NotImplementedError("Base container class don't implement this")

    def _parse_pattern(self, value: str) -> List[str]:
        """list: Safely parse include/exclude pattern from user"""
        if not value:
            return None

        if type(value) is not str:
            return None

        value = value.strip()
        if len(value) == 0:
            return None

        return value.split(',')

    def __eq__(self, other):
        """Compare container by id"""
        if other is None:
            return False

        if not isinstance(other, Container):
            return False

        return self.id == other.id

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "<Container {}>".format(self.name)


class Mount:
    """Represents a volume mount (volume or bind)"""
    def __init__(self, data, container=None):
        self._data = data
        self._container = container

    @property
    def container(self) -> Container:
        """The container this mount belongs to"""
        return self._container

    @property
    def type(self) -> str:
        """bind/volume"""
        return self._data.get('Type')

    @property
    def name(self) -> str:
        """Name of the mount"""
        return self._data.get('Name')

    @property
    def source(self) -> str:
        """Source of the mount. Volume name or path"""
        return self._data.get('Source')

    @property
    def destination(self) -> str:
        """Destination path for the volume mount in the container"""
        return self._data.get('Destination')

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self._data)

    def __hash__(self):
        """Uniqueness for a volume"""
        if self.type == VOLUME_TYPE_VOLUME:
            return hash(self.name)
        elif self.type == VOLUME_TYPE_BIND:
            return hash(self.source)
        else:
            raise ValueError("Unknown volume type: {}".format(self.type))


class RunningContainers:

    def __init__(self):
        all_containers = utils.list_containers()
        self.containers = []
        self.this_container = None
        self.backup_process_container = None

        # Find the container we are running in.
        # If we don't have this information we cannot continue
        for container_data in all_containers:
            if container_data.get('Id').startswith(os.environ['HOSTNAME']):
                self.this_container = Container(container_data)

        if not self.this_container:
            raise ValueError("Cannot find metadata for backup container")

        # Gather all containers in the current compose setup
        for container_data in all_containers:
            container = Container(container_data)

            # Detect running backup process container
            if container.is_backup_process_container:
                self.backup_process_container = container

            # Detect containers belonging to the current compose setup
            if (container.project_name == self.this_container.project_name
               and not container.is_oneoff):
                if container.id != self.this_container.id:
                    self.containers.append(container)

    @property
    def project_name(self) -> str:
        """str: Name of the compose project"""
        return self.this_container.project_name

    @property
    def backup_process_running(self) -> bool:
        """Is the backup process container running?"""
        return self.backup_process_container is not None

    def containers_for_backup(self):
        """Obtain all containers with backup enabled"""
        return [container for container in self.containers if container.backup_enabled]

    def generate_backup_mounts(self, dest_prefix='/backup') -> dict:
        """Generate mounts for backup for the entire compose setup"""
        mounts = {}
        for container in self.containers_for_backup():
            if container.volume_backup_enabled:
                mounts.update(container.volumes_for_backup(source_prefix=dest_prefix, mode='ro'))

        return mounts

    def get_service(self, name) -> Container:
        for container in self.containers:
            if container.service_name == name:
                return container

        return None