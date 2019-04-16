import json
import os
import unittest
from unittest import mock

from restic_volume_backup import utils
from restic_volume_backup.containers import RunningContainers
import fixtures

list_containers_func = 'restic_volume_backup.utils.list_containers'


class ResticBackupTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up basic enviroment variables"""
        os.environ['RESTIC_REPOSITORY'] = "test"
        os.environ['RESTIC_PASSWORD'] = "password"

    def createContainers(self):
        backup_hash = fixtures.generate_sha256()
        os.environ['HOSTNAME'] = backup_hash[:8]
        return [
            {
                'id': backup_hash,
                'service': 'backup',
            }
        ]

    def test_list_containers(self):
        """Test a basic container list"""
        containers = [
            {
                'service': 'web',
                'labels': {
                    'moo': 1,
                },
                'mounts': [{
                    'Source': 'moo',
                    'Destination': 'moo',
                    'Type': 'bind',
                }]
            },
            {
                'service': 'mysql',
            },
            {
                'service': 'postgres',
            },
        ]

        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            test = utils.list_containers()

    def test_running_containers(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'test': 'test',
                },
                'mounts': [{
                    'Source': 'test',
                    'Destination': 'test',
                    'Type': 'bind',
                }]
            },
            {
                'service': 'mysql',
            },
            {
                'service': 'postgres',
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            result = RunningContainers()
            self.assertEqual(len(result.containers), 3, msg="Three containers expected")
            self.assertNotEqual(result.this_container, None, msg="No backup container found")

    def test_include(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'restic-volume-backup.include': 'media',
                },
                'mounts': [
                    {
                        'Source': '/srv/files/media',
                        'Destination': '/srv/media',
                        'Type': 'bind',
                    },
                    {
                        'Source': '/srv/files/stuff',
                        'Destination': '/srv/stuff',
                        'Type': 'bind',
                    },
                ]
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()

        web_service = cnt.get_service('web')
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = list(web_service.filter_mounts())
        self.assertEqual(len(mounts), 1)
        raise ValueError(mounts)

    def test_exclude(self):
        pass