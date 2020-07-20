# Copyright (C) 2015 Linaro Limited
#
# Author: Senthil Kumaran S <senthil.kumaran@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import os
import glob
import unittest
from lava_dispatcher.device import NewDevice
from lava_dispatcher.parser import JobParser
from lava_dispatcher.action import JobError
from lava_dispatcher.protocols.lxc import LxcProtocol
from lava_dispatcher.test.test_basic import Factory, StdoutTestCase
from lava_dispatcher.test.utils import DummyLogger, infrastructure_error, infrastructure_error_multi_paths
from lava_dispatcher.actions.deploy import DeployAction
from lava_dispatcher.actions.deploy.fastboot import FastbootFlashOrderAction
from lava_dispatcher.actions.boot.fastboot import BootAction
from lava_dispatcher.utils.lxc import is_lxc_requested, lxc_cmd_prefix


class FastBootFactory(Factory):  # pylint: disable=too-few-public-methods
    """
    Not Model based, this is not a Django factory.
    Factory objects are dispatcher based classes, independent
    of any database objects.
    """

    def create_fastboot_job(self, filename):
        return self.create_job('nexus4-01.jinja2', filename)

    def create_db410c_job(self, filename):
        return self.create_job('db410c-01.jinja2', filename)

    def create_x15_job(self, filename):
        return self.create_job('x15-01.jinja2', filename)

    def create_hikey_job(self, filename):
        return self.create_job('hi6220-hikey-r2-01.jinja2', filename)

    def create_hikey960_job(self, filename):
        return self.create_job('hi960-hikey-01.jinja2', filename)

    def create_nexus5x_job(self, filename):
        return self.create_job('nexus5x-01.jinja2', filename)

    def create_pixel_job(self, filename):
        return self.create_job('pixel-01.jinja2', filename)


class TestFastbootDeploy(StdoutTestCase):  # pylint: disable=too-many-public-methods

    def setUp(self):
        super().setUp()
        self.factory = FastBootFactory()
        self.job = self.factory.create_fastboot_job('sample_jobs/fastboot.yaml')

    def test_deploy_job(self):
        self.assertEqual(self.job.pipeline.job, self.job)
        self.assertIsInstance(self.job.device['device_info'], list)
        for action in self.job.pipeline.actions:
            if isinstance(action, DeployAction):
                self.assertEqual(action.job, self.job)

    def test_pipeline(self):
        description_ref = self.pipeline_reference('fastboot.yaml')
        self.assertEqual(description_ref, self.job.pipeline.describe(False))

    @unittest.skipIf(infrastructure_error_multi_paths(
        ['lxc-info', 'img2simg', 'simg2img']),
        "lxc or img2simg or simg2img not installed")
    def test_lxc_api(self):
        job = self.factory.create_hikey_job('sample_jobs/hikey-oe.yaml')
        description_ref = self.pipeline_reference('hikey-oe.yaml', job=job)
        job.validate()
        self.assertEqual(description_ref, job.pipeline.describe(False))
        self.assertIn(LxcProtocol.name, [protocol.name for protocol in job.protocols])
        self.assertEqual(len(job.protocols), 1)
        self.assertIsNotNone(job.device.pre_os_command)
        select = [action for action in job.pipeline.actions if action.name == 'grub-sequence-action'][0]
        self.assertIn(LxcProtocol.name, select.parameters.keys())
        self.assertIn('protocols', select.parameters.keys())
        self.assertIn(LxcProtocol.name, select.parameters['protocols'].keys())
        self.assertEqual(len(select.parameters['protocols'][LxcProtocol.name]), 1)
        lxc_active = any([protocol for protocol in job.protocols if protocol.name == LxcProtocol.name])
        self.assertTrue(lxc_active)
        for calling in select.parameters['protocols'][LxcProtocol.name]:
            self.assertEqual(calling['action'], select.name)
            self.assertEqual(calling['request'], 'pre-os-command')
        deploy = [action for action in job.pipeline.actions if action.name == 'fastboot-deploy'][0]
        self.assertIn(LxcProtocol.name, deploy.parameters.keys())
        self.assertIn('protocols', deploy.parameters.keys())
        self.assertIn(LxcProtocol.name, deploy.parameters['protocols'].keys())
        self.assertEqual(len(deploy.parameters['protocols'][LxcProtocol.name]), 1)
        for calling in deploy.parameters['protocols'][LxcProtocol.name]:
            self.assertEqual(calling['action'], deploy.name)
            self.assertEqual(calling['request'], 'pre-power-command')
        pair = ['pre-os-command', 'pre-power-command']
        action_list = {list(jaction.keys())[0] for jaction in job.parameters['actions']}
        block = job.parameters['actions']
        for action in action_list:
            for item in block:
                if action in item:
                    if 'protocols' in item[action]:
                        caller = (item[action]['protocols'][LxcProtocol.name])
                        for call in caller:
                            self.assertIn(call['request'], pair)

    @unittest.skipIf(infrastructure_error('lxc-info'), "lxc-info not installed")
    def test_fastboot_lxc(self):
        job = self.factory.create_hikey_job('sample_jobs/hi6220-hikey.yaml')

        description_ref = self.pipeline_reference('hi6220-hikey.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        self.assertEqual(
            job.device.pre_power_command,
            '/home/neil/lava-lab/shared/lab-scripts/usb_hub_control -u 12 -p 4000 -m sync')
        lxc_deploy = [action for action in job.pipeline.actions if action.name == 'lxc-deploy'][0]
        overlay = [action for action in lxc_deploy.internal_pipeline.actions if action.name == 'lava-overlay'][0]
        testdef = [action for action in overlay.internal_pipeline.actions if action.name == 'test-definition'][0]
        job.validate()
        self.assertEqual(
            {
                '1.8.4.20': '4_android-optee',
                '1.8.4.4': '0_get-adb-serial',
                '1.8.4.12': '2_android-busybox',
                '1.8.4.8': '1_android-meminfo',
                '1.8.4.16': '3_android-ping-dns'},
            testdef.get_namespace_data(action='test-runscript-overlay', label='test-runscript-overlay', key='testdef_levels'))
        for testdef in testdef.test_list[0]:
            self.assertEqual('git', testdef['from'])

    @unittest.skipIf(infrastructure_error('lxc-create'),
                     'lxc-create not installed')
    def test_validate(self):
        try:
            self.job.pipeline.validate_actions()
        except JobError as exc:
            self.fail(exc)
        for action in self.job.pipeline.actions:
            self.assertEqual([], action.errors)

    def test_overlay(self):
        overlay = None
        for action in self.job.pipeline.actions:
            self.assertIsNotNone(action.name)
            if isinstance(action, DeployAction):
                if action.parameters['namespace'] == 'tlxc':
                    overlay = [action for action in action.pipeline.actions if action.name == 'lava-overlay'][0]
        self.assertIsNotNone(overlay)
        # these tests require that lava-dispatcher itself is installed, not just running tests from a git clone
        self.assertTrue(os.path.exists(overlay.lava_test_dir))
        self.assertIsNot(overlay.lava_test_dir, '/')
        self.assertNotIn('lava_multi_node_test_dir', dir(overlay))
        self.assertNotIn('lava_multi_node_cache_file', dir(overlay))
        self.assertNotIn('lava_lmp_test_dir', dir(overlay))
        self.assertNotIn('lava_lmp_cache_file', dir(overlay))
        self.assertIsNotNone(overlay.parameters['deployment_data']['lava_test_results_dir'])
        self.assertIsNotNone(overlay.parameters['deployment_data']['lava_test_sh_cmd'])
        self.assertEqual(overlay.parameters['deployment_data']['distro'],
                         'debian')
        self.assertIsNotNone(overlay.parameters['deployment_data']['lava_test_results_part_attr'])
        self.assertIsNotNone(glob.glob(os.path.join(overlay.lava_test_dir, 'lava-*')))

    @unittest.skipIf(infrastructure_error('lxc-attach'),
                     'lxc-attach not installed')
    def test_boot(self):
        for action in self.job.pipeline.actions:
            if isinstance(action, BootAction):
                # get the action & populate it
                if action.parameters.get('namespace') == 'tlxc':
                    self.assertIn(action.parameters['method'],
                                  ['lxc', 'fastboot'])
                    self.assertEqual(action.parameters['prompts'],
                                     ['root@(.*):/#'])
                if action.parameters.get('namespace') == 'droid':
                    self.assertIn(action.parameters['method'],
                                  ['lxc', 'fastboot'])
                    self.assertEqual(action.parameters.get('prompts'), None)

    def test_testdefinitions(self):
        for action in self.job.pipeline.actions:
            if action.name == 'test':
                # get the action & populate it
                self.assertEqual(len(action.parameters['definitions']), 2)

    def test_udev_actions(self):
        self.factory = FastBootFactory()
        job = self.factory.create_db410c_job('sample_jobs/db410c.yaml')
        self.assertTrue(job.device.get('fastboot_via_uboot', True))
        description_ref = self.pipeline_reference('db410c.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        boot = [action for action in job.pipeline.actions if action.name == 'fastboot-boot'][0]

    def test_x15_job(self):
        self.factory = FastBootFactory()
        job = self.factory.create_x15_job('sample_jobs/x15.yaml')
        job.validate()
        description_ref = self.pipeline_reference('x15.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        deploy = [action for action in job.pipeline.actions if action.name == 'fastboot-deploy'][0]
        enter = [action for action in deploy.internal_pipeline.actions if action.name == 'uboot-enter-fastboot'][0]
        interrupt = [action for action in enter.internal_pipeline.actions if action.name == 'bootloader-interrupt'][0]
        self.assertTrue(interrupt.needs_interrupt)
        self.assertIsInstance(interrupt.params, dict)
        self.assertNotEqual(interrupt.params, {})
        self.assertIn('mkimage_arch', interrupt.params)
        self.assertIn('interrupt_prompt', interrupt.params)
        boot = [action for action in job.pipeline.actions if action.name == 'fastboot-boot'][0]
        enter = [action for action in boot.internal_pipeline.actions if action.name == 'uboot-enter-fastboot'][0]
        interrupt = [action for action in enter.internal_pipeline.actions if action.name == 'bootloader-interrupt'][0]
        self.assertIsInstance(interrupt.params, dict)
        self.assertNotEqual(interrupt.params, {})
        self.assertIn('mkimage_arch', interrupt.params)
        self.assertIn('interrupt_prompt', interrupt.params)
        self.assertTrue(interrupt.needs_interrupt)
        autologin = [action for action in boot.internal_pipeline.actions if action.name == 'auto-login-action'][0]
        self.assertTrue(autologin.booting)
        self.assertEqual(set(autologin.parameters.get('prompts')), set(['root@(.*):/#', 'shell@am57xevm:/']))
        self.assertIsNone(autologin.parameters.get('boot_message'))

    def test_nexus5x_job(self):
        self.factory = FastBootFactory()
        job = self.factory.create_nexus5x_job('sample_jobs/nexus5x.yaml')
        # do not run job.validate() - urls no longer exist.
        description_ref = self.pipeline_reference('nexus5x.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))

    def test_pixel_job(self):
        self.factory = FastBootFactory()
        job = self.factory.create_pixel_job('sample_jobs/pixel.yaml')
        # do not run job.validate() - urls no longer exist.
        description_ref = self.pipeline_reference('pixel.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))

    def test_flash_cmds_order(self):
        self.factory = FastBootFactory()
        job = self.factory.create_db410c_job('sample_jobs/db410c.yaml')
        # The expected_flash_cmds list ensures the following:
        # 1. Order of flash commands.
        # 2. Number / Count of flash commands.
        # 3. 'cdt' flash command is not part of draganboard-410c's device
        #    dictionary, but ensure that it gets added in the final flash
        #    commands list.
        expected_flash_cmds = ['partition', 'hyp', 'rpm', 'sbl1', 'tz',
                               'aboot', 'cdt', 'boot', 'rootfs']
        flash_order = None
        for action in job.pipeline.actions:
            self.assertIsNotNone(action.name)
            if isinstance(action, DeployAction):
                if action.name == 'fastboot-deploy':
                    flash_order = [action for action in
                                   action.pipeline.actions if action.name ==
                                   'fastboot-flash-order-action'][0]
                    flash_cmds = [action.command for action in
                                  flash_order.pipeline.actions if
                                  action.name == 'fastboot-flash-action']
        self.assertIsNotNone(flash_order)
        self.assertIsInstance(flash_order, FastbootFlashOrderAction)
        self.assertEqual(expected_flash_cmds, flash_cmds)

    def test_hikey960_fastboot(self):
        job = self.factory.create_hikey960_job('sample_jobs/hikey960-aosp.yaml')
        self.assertIsNotNone(job)
        job.validate()
        description_ref = self.pipeline_reference('hi960-aosp-efi.yaml', job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        flash_order = None
        expected_flash_cmds = ['boot', 'system', 'userdata', 'cache']
        for action in job.pipeline.actions:
            self.assertIsNotNone(action.name)
            if isinstance(action, DeployAction):
                if action.name == 'fastboot-deploy':
                    flash_order = [action for action in
                                   action.pipeline.actions if action.name ==
                                   'fastboot-flash-order-action'][0]
                    flash_cmds = [action.command for action in
                                  flash_order.pipeline.actions if
                                  action.name == 'fastboot-flash-action']
        self.assertIsNotNone(flash_order)
        self.assertIsInstance(flash_order, FastbootFlashOrderAction)
        self.assertEqual(expected_flash_cmds, flash_cmds)

    def test_fastboot_minus_lxc(self):
        # Do not run job.validate() since it will require some android tools
        # such as fastboot, adb, etc. to be installed.
        job = self.factory.create_fastboot_job(
            'sample_jobs/nexus4-minus-lxc.yaml')
        description_ref = self.pipeline_reference('nexus4-minus-lxc.yaml',
                                                  job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        # There shouldn't be any lxc defined
        lxc_name = is_lxc_requested(job)
        self.assertEqual(lxc_name, False)
        deploy = [action for action in job.pipeline.actions
                  if action.name == 'fastboot-deploy'][0]
        # No lxc requested, hence lxc_cmd_prefix is an empty list
        self.assertEqual([], lxc_cmd_prefix(job))

    def test_db410c_minus_lxc(self):
        # Do not run job.validate() since it will require some android tools
        # such as fastboot, adb, etc. to be installed.
        job = self.factory.create_db410c_job(
            'sample_jobs/db410c-minus-lxc.yaml')
        description_ref = self.pipeline_reference('db410c-minus-lxc.yaml',
                                                  job=job)
        self.assertEqual(description_ref, job.pipeline.describe(False))
        # There shouldn't be any lxc defined
        lxc_name = is_lxc_requested(job)
        self.assertEqual(lxc_name, False)
        deploy = [action for action in job.pipeline.actions
                  if action.name == 'fastboot-deploy'][0]
        # No lxc requested, hence lxc_cmd_prefix is an empty list
        self.assertEqual([], lxc_cmd_prefix(job))
