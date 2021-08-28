import os
import shutil
from zipfile import ZipFile
import DDG_Tracker

if DDG_Tracker.DEBUG:
	print("disable the debug you doofus")
	input()

os.system(r'pyinstaller --onefile --add-data C:\Users\tryne\Anaconda3\DLLs\libcrypto-1_1-x64.dll;. --add-data C:\Users\tryne\Anaconda3\DLLs\libssl-1_1-x64.dll;. DDG_Tracker.py')
os.system(r'pyinstaller --onefile --add-data C:\Users\tryne\Anaconda3\DLLs\libcrypto-1_1-x64.dll;. --add-data C:\Users\tryne\Anaconda3\DLLs\libssl-1_1-x64.dll;. Updater.py')

versionFile = open('versionnum', 'r')
versionNum = float(versionFile.read())
versionFile.close()
versionFile = open('versionnum', 'w')
versionNum += .1
versionFile.write(str(versionNum))
versionFile.close()
shutil.copyfile('versionnum', "./dist/release/versionnum")
shutil.copyfile('./dist/Updater.exe', "./dist/release/Updater.exe")
shutil.copyfile('./dist/DDG_Tracker.exe', "./dist/release/DDG_Tracker.exe")

zipOut = ZipFile("./dist/release/SBBTracker.zip", 'w')
zipOut.write("./dist/release/versionnum", arcname="versionnum")
zipOut.write("./dist/release/Updater.exe", arcname="Updater.exe")
zipOut.write("./dist/release/DDG_Tracker.exe", arcname="DDG_Tracker.exe")
print("done")