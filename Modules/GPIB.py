import TermOut.Logging as Logging
try:
	import gpib
except ImportError:
	Logging.error("linux_gpib not installed or Python bindings not built")
	exit(1)
from TermOut.ProgressBar import ProgressBar
import os
import subprocess
import time



class GPIB:
	def __init__(self, sad=0, timeout=13, send_eoi=1, eos_mode=0, debug=False):
		self.debug = debug
		self.devices = {}
		self.drivers = {}
		self.started = True
		self.reset_usb_controller()
		# Interface ids are used to determine which usb connections need to be reset
		# Example:
		"""
		Bus 001 Device 006: ID 3923:709b National Instruments Corp. GPIB-USB-HS
		"""
		self.interfaces = ["3923:709b", "0957:0518"]
		if os.geteuid() != 0:
			Logging.error("You need to have root privileges to run this script.")
			self.started = False
			exit(1)
		self.reset_interfaces()
		Logging.header("Starting discovery of scientific devices that do stuff")
		progress_bar = ProgressBar(30)
		discovered = {}
		for pad in range(0, 31):
			id = gpib.dev(0, pad, sad, timeout, send_eoi, eos_mode)
			try:
				gpib.clear(id)
				gpib.write(id, "*IDN?")
				device_id = gpib.read(id, 1024).rstrip()
				self.devices[pad] = GenericDriver(GPIBCommunicator(id, self.reset_interfaces))
				discovered[id] = device_id
			except gpib.GpibError:
				pass
			progress_bar.update(pad)
		for i in discovered:
			Logging.header("%s on %s" % (discovered[i], i - 16))
		Logging.success("Discovery finished successfully!")


	def __del__(self):
		for i in self.devices:
			gpib.close(i.communicator.id)
		self.reset_usb()


	def reset_usb_controller(self):
		if self.debug: Logging.warning("Resetting usb controller")
		if open("/etc/issue").read() == 'Debian GNU/Linux 8 \\n \\l\n\n':
			self.reset_debian()


	def reset_debian(self):
		ehci_content = os.listdir("/sys/bus/pci/drivers/ehci-pci/")
		for i in ehci_content:
			if i[0] == "0":
				os.system('echo -n %s | sudo tee /sys/bus/pci/drivers/ehci-pci/unbind' % i)
				os.system('echo -n %s | sudo tee /sys/bus/pci/drivers/ehci-pci/bind' % i)


	def reset_usb(self):
		if self.debug: Logging.info("Resetting connected usb interfaces")
		for i in subprocess.check_output(["lsusb"]).split("\n"):
			for k in self.interfaces:
				if k in i:
					try:
						subprocess.check_output(["sudo", "usbreset", "/dev/bus/usb/%s/%s" % (i[4:7], i[15:18])])
					except subprocess.CalledProcessError:
						self.reset_usb_controller()




	# If the interface get's stuck this function is used to reset it 
	def reset_interfaces(self, calls=0):
		if self.debug: Logging.info("Resetting connected interfaces")
		self.reset_usb()
		time.sleep(2)
		if self.debug: Logging.info("Running gpib_config")
		try:
			subprocess.check_call(["sudo", "gpib_config"])
		except subprocess.CalledProcessError:
			if calls == 2:
				Logging.error("No interface connected")
				exit(1)
			self.reset_interfaces(calls=calls + 1)
		time.sleep(2)


class GPIBCommunicator:
	def __init__(self, id, reset, debug=False):
		self.id = id
		self.reset = reset
		self.last_write = ""

	def __str__(self):
		return "GPIB adress: %s" % self.id

	def command(self, str):
		gpib.command(self.id, str)


	def config(self, option, value):
		self.res = gpib.config(self.id, option, value)
		return self.res


	def interface_clear(self):
		gpib.interface_clear(self.id)


	def write(self, str, calls=0):
		try:
			gpib.write(self.id, str)
			self.last_write = str
		except gpib.GpibError:
			if calls == 2:
				Logging.error("Unrecoverable error. Please reboot")
				raw_input("Press ENTER when done.")
				exit(1)
			self.reset()
			self.write(str, calls=calls + 1)


	def write_async(self, str):
		gpib.write_async(self.id, str)


	def read(self, len=512, calls=0):
		try:
			result = gpib.read(self.id, len).rstrip("\n")
		except gpib.GpibError, e:
			Logging.warning(str(e))
			if str(e) == "read() failed: A read or write of data bytes has been aborted, possibly due to a timeout or reception of a device clear command.":
				Logging.info("Last write didn't succeed. Resending...")
				self.reset()
				self.write(self.last_write)
			if calls == 2:
				Logging.error("Unrecoverable error. Please reboot")
				raw_input("Press ENTER when done.")
				exit(1)
			self.reset()
			result = self.read(calls=calls + 1)
		return result


	def listener(self, pad, sad=0):
		self.res = gpib.listener(self.id, pad, sad)
		return self.res


	def ask(self,option):
		self.res = gpib.ask(self.id, option)
		return self.res


	def clear(self):
		gpib.clear(self.id)


	def wait(self, mask):
		gpib.wait(self.id, mask)


	def serial_poll(self):
		self.spb = gpib.serial_poll(self.id)
		return self.spb


	def trigger(self):
		gpib.trigger(self.id)


	def remote_enable(self, val):
		gpib.remote_enable(self.id, val)


	def ibloc(self):
		self.res = gpib.ibloc(self.id)
		return self.res


	def ibsta(self):
		self.res = gpib.ibsta()
		return self.res


	def ibcnt(self):
		self.res = gpib.ibcnt()
		return self.res


	def timeout(self, value):
		return gpib.timeout(self.id, value)



class GenericDriver(GPIBCommunicator):
	def __init__(self, communicator):
		self.communicator = communicator


	def get(self, cmd):
		self.communicator.write(cmd)
		return self.communicator.read(1024)



if __name__ == "__main__":
	g = GPIB()
	if len(g.devices.keys()) > 0:
		Logging.header("Starting command line (^C to quit)")
		try:
			while 1:
				print(g.devices[2].get(raw_input("> ")))
		except KeyboardInterrupt:
			pass