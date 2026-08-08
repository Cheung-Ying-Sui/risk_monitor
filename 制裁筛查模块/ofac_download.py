import requests

url = "Published/6258a10e-a1b3-4902-9b8e-4feee677b59d/2026-07-16/b3b992c3-a25c-4c09-8dc7-8af257522104/SDN_ADVANCED.XML"


response = requests.get(url)


with open(
    "data/sdn.xml",
    "wb"
) as f:
    f.write(response.content)


print("Download completed")