#! /usr/bin/env/ python3
# -*- coding:utf-8-*-

# SMBus (System Management Bus) is a subset from the I2C protocol
# When writing a driver for an I2C device try to use the SMBus commands
# if possible (if the device uses only that subset of the I2C protocol)
# as it makes it possible to use the device driver on both SMBus
# adapters and I2C adapters.
# https://www.kernel.org/doc/Documentation/i2c/smbus-protocol
import smbus
import time
import math

#Datasheet: http://www.datasheetspdf.com/PDF/BMP180/770150/1
class BMP180:
	def __init__(self):
	
		# 0 = /dev/i2c-0 (port I2C0)
		# 1 = /dev/i2c-1 (port I2C1)
		self._bus = smbus.SMBus(1)
		
		#7 bit address (will be left shifted to add the read write bit)
		self._sensor = 0x77  
		
		# see page 22 of datasheet
		# To read out the temperature data word UT (16 bit), the pressure data word UP (16 to 19 bit)
		# Temperature or pressure value UT or UP 0xF6 (MSB), 0xF7 (LSB), optionally 0xF8 (XLSB)
		self._register = {'CALIB': 0xAA,
						  'MEET': 0xF4,
						  'MSB': 0xF6,
						  'LSB': 0xF7}
						  
		self._calib = {'AC1' : 0,
					   'AC2' : 0,
					   'AC3' : 0,
					   'AC4' : 0,
					   'AC5' : 0,
					   'AC6' : 0,
					   'B1' : 0,
					   'B2' : 0,
					   'MB' : 0,
					   'MC' : 0,
					   'MD' : 0}
		 
		# oversampling 0, 1, 2, of 3
		self._oss = 3
		
		# Control registers values for different internal oversampling_setting (oss)
		# TEMP - Temperature
		# OSS - Pressure
		self._crv = {'TEMP' : 0x2E,
				     '0SS0' : 0x34,
				     '0SS1' : 0x74,
				     '0SS2' : 0xB4,
				     '0SS3' : 0xF4}

		#temperature
		self._temp = 0 		
		
		#pressure
		self._druk = 0
				
	def _signed(self, mb, lb):
		tmp = 256 * mb + lb
		if(tmp > 32767):
			tmp -= 65536
		return tmp
				
	def _unsigned(self, mb, lb):
		return 256 * mb + lb
		
	def meet(self):
		if(self._leesCalib()):
			self._meetDruk(self._meetTemp())
			return '%0.01f;%0.02f' % (self._temp, self._druk)
		else:
			return '0;0'
			

	
	def _leesCalib(self):
		try:
			calibDta = self._bus.read_i2c_block_data(self._sensor, self._register['CALIB'], 22)
			
			#see page 15 of datasheet
			items = [['AC1',True],  # short
				['AC2',True],  # short
				['AC3',True],  # short
				['AC4',False], #unsigned short
				['AC5',False], #unsigned short
				['AC6',False], #unsigned short
				['B1',True],   # short
				['B2',True],   # short 
				['MB',True],   # short
				['MC',True],   # short
				['MD',True]]   # short 				
			
			for ndx, el in enumerate(items):
				if(el[1]):
					tmp = self._signed(calibDta[2*ndx], calibDta[2*ndx+1])
				else:
					tmp = self._unsigned(calibDta[2*ndx], calibDta[2*ndx+1])
				self._calib[el[0]] = tmp
			return True
			
		except IOError:
			return false
	
	# see datasheet page 15 
	# calculate true temperature
	def _meetTemp(self):
		self._bus.write_byte_data(self._sensor, self._register['MEET'], self._crv['TEMP'])
		
		time.sleep(0.005)
		
		(mb,lb) = self._bus.read_i2c_block_data(self._sensor, self._register['MSB'], 2)
		
		ut = 256 * mb + lb
		
		# calculate true temperature x1 = (ut-AC6)*QC5/2 power 15
		x1 = (ut - self._calib['AC6']) * self._calib['AC5']/math.pow(2,15)
		
		# calculate true temperature x2 = (MC*2 power 11)/ X1
		x2 = self._calib['MC'] * math.pow(2,11)/(x1 + self._calib['MD'])
		
		b5 = x1 + x2
		self._temp = (b5 + 8) / (10 * math.pow(2,4))
		return b5
		
	# calculate true pressure (look in datasheet)
	def _meetDruk(self, b5):
		#print('b5: %1d' %b5)
		
		oss_name = '0SS%1d' % (self._oss)
		#print('oss_name: ' + oss_name)
		
		self._bus.write_byte_data(self._sensor, self._register['MEET'], self._crv[oss_name])
		
		time.sleep(0.03)
		
		(bt0, bt1, bt2) = self._bus.read_i2c_block_data(self._sensor, self._register['MSB'],3)
		up = (math.pow(2,16) * bt0 + math.pow(2,8) * bt1 + bt2) / math.pow(2,8-self._oss)		
		#print('up:', up)
		
		b6 = b5 - 4000
		#print('b6:', b6)
		
		x1 = (self._calib['B2'] * (b6 * b6 / math.pow(2,12)))/math.pow(2,11)
		#print('x1:', x1)
		
		x2 = self._calib['AC2'] * b6 / math.pow(2,11)
		#print('x2:', x2)
		
		x3 = x1 + x2
		#print('x3:', x3)
		
		b3 = ((( 4 * self._calib['AC1'] + x3) * math.pow(2, self._oss)) + 2) / 4
		#print('b3:', b3)
		
		x1 = self._calib['AC3'] * b6 / math.pow(2,13)
		#print('x1: %1d' %x1)
		
		x2 = (self._calib['B1'] * (b6 * b6 / math.pow(2,12))) / math.pow(2,16)
		#print('x2: %1d' %x2)
		
		x3 = (2 + x1 + x2) / 4
		#print('x3: %1d' %x3)
		
		# why different?
		b4 = self._calib['AC4'] * (x3 + math.pow(2,15)) / math.pow(2,15)
		#print('self._calib AC4:', self._calib['AC4'])
		#print('b4:', b4)
		
		b7 = (up - b3) * (50000/math.pow(2,self._oss))
		#print('b7: %1d' %b7)
		
		# always else
		p = (b7 / b4) * 2
		#print('p:', p)
		
		x1 = p * p / math.pow(2,16)
		#print('x1: %1d' %x1)
		
		x1 = (x1 * 3038) / math.pow(2,16)
		#print('x1: %1d' %x1)
		
		x2 = (-7357 * p) / math.pow(2,16)
		#print('x2: %1d' %x2)
		
		# why divided by 100?
		p = (p + (x1 + x2 + 3791) / math.pow(2,4)) / 100
		#print('p:', p)
		
		self._druk = p
		#print('self._druk: %1d' %self._druk)
		
		
		
bmp =  BMP180()
print (bmp.meet())		
