import re
import platform

from virttest import libvirt_version
from virttest import utils_misc

from virttest.libvirt_xml.devices import memory
from virttest.utils_version import VersionInterval

from avocado.core import exceptions


def convert_data_size(current_size, dest_unit="KiB"):
    """
    Convert source value to expected value

    :param current_size: current size str, eg: 1024MB
    :param dest_unit: dest size unit, eg: KiB, MiB
    :return: dest_size: The size is converted, eg: 1(the dest unit is given,
    so it means 1GB)
    """
    decimal = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    binary = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    current_value = re.findall(r"\d+", current_size)[0]
    current_unit = re.findall(r"\D+", current_size)[0]

    if current_unit == "bytes":
        bytes_size = int(current_value)
    else:
        factor, unit_list = 0, []
        if current_unit in decimal:
            factor = 1000
            unit_list = decimal
        elif current_unit in binary:
            factor = 1024
            unit_list = binary
        else:
            raise exceptions.TestError("The unit:%s you input is not "
                                       "found" % current_unit)
        bytes_size = int(current_value) * (
                    factor ** (unit_list.index(current_unit)))

    if dest_unit in decimal:
        factor = 1000
        unit_list = decimal
    elif dest_unit in binary:
        factor = 1024
        unit_list = binary
    else:
        raise exceptions.TestError(
            "The unit:%s you input is not found" % current_unit)

    dest_size = bytes_size / (factor ** (unit_list.index(dest_unit)))
    if isinstance(dest_size, float):
        return dest_size
    return int(dest_size)


def check_supported_version(params, test, vm):
    """
    Check the supported version

    :param params: Dictionary with the test parameters
    :param test: Test object
    :param vm: Vm object
    """
    guest_required_kernel = params.get('guest_required_kernel')
    libvirt_version.is_libvirt_feature_supported(params)
    utils_misc.is_qemu_function_supported(params)
    if not guest_required_kernel:
        return

    if not vm.is_alive():
        vm.start()
    vm_session = vm.wait_for_login()
    vm_kerv = vm_session.cmd_output('uname -r').strip().split('-')[0]
    vm_session.close()
    if vm_kerv not in VersionInterval(guest_required_kernel):
        test.cancel("Got guest kernel version:%s, which is not in %s" %
                    (vm_kerv, guest_required_kernel))


def prepare_mem_obj(dest_dict):
    """
    Prepare memory object
    :param dest_dict: dimm memory dict.
    :return mem_obj, memory object.
    """
    mem_obj = memory.Memory()
    mem_obj.setup_attrs(**dest_dict)

    return mem_obj


def create_file_within_nvdimm_disk(test, vm_session, test_device, test_file,
                                   mount_point, error_msg="", test_str="test_text",
                                   block_size=4096):
    """
    Create a test file in the nvdimm file disk

    :param test: test object
    :param vm_session: VM session
    :param test_device: str, device value
    :param test_file: str, file name to be used
    :param mount_point: mount point path.
    :param error_msg: Error msg content when useing mkfs cmd
    :param test_str: str to be written into the nvdimm file disk
    :param block_size: int, block size for mkfs.xfs -b
    """
    # Create a file system
    bsize_str = '-b size={}'.format(block_size) if block_size != 0 else ''
    if any(platform.platform().find(ver) for ver in ('el8', 'el9')):
        cmd = 'mkfs.xfs -f {} {} -m reflink=0'.format(test_device, bsize_str)
    else:
        cmd = 'mkfs.xfs -f {} {}'.format(test_device, bsize_str)

    vm_session.cmd("mkdir -p %s" % mount_point)
    output = vm_session.cmd_output(cmd)
    if error_msg:
        if error_msg not in output:
            test.fail("Expect to get '%s' in '%s'" % (error_msg, output))
        else:
            return
    test.log.debug("Command '%s' output:%s", cmd, output)

    # Mount the file system
    uuid = re.findall(
        r' UUID="(\S+)"', vm_session.cmd_output('blkid %s' % test_device))[0]
    vm_session.cmd_status_output('mount -o dax -U {} {}'.format(uuid, mount_point))

    cmd = 'echo \"%s\" >%s' % (test_str, test_file)
    vm_session.cmd(cmd)
    vm_session.cmd_output('umount %s' % mount_point)
