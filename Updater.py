import requests
from zipfile import ZipFile
from subprocess import Popen

def update():
	req = requests.get("https://datadrivengaming.net/sbb/tracker")
	file = req.content
	f = open("dist.zip", 'wb')
	f.write(file)
	f.close()
	with ZipFile("dist.zip", 'r') as f:
		f.extract("DDG_Tracker.exe")
		f.extract("versionnum")
		print("Done")

if __name__ == "__main__":
	print("Updating")
	update()
	Popen('./DDG_Tracker.exe')

