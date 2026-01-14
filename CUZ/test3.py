import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import exifread
import webbrowser

# ---------- EXIF Extraction ----------
def extract_exif_pillow(image_path):
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if not exif_data:
            return {}
        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                gps_data = {}
                for t in value:
                    sub_tag = GPSTAGS.get(t, t)
                    gps_data[sub_tag] = value[t]
                exif["GPSInfo"] = gps_data
            else:
                exif[tag] = value
        return exif
    except Exception:
        return {}

def extract_exif_exifread(image_path):
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        gps_info = {}
        if "GPS GPSLatitude" in tags and "GPS GPSLongitude" in tags:
            gps_info["GPSLatitude"] = tags["GPS GPSLatitude"]
            gps_info["GPSLatitudeRef"] = tags.get("GPS GPSLatitudeRef", "N")
            gps_info["GPSLongitude"] = tags["GPS GPSLongitude"]
            gps_info["GPSLongitudeRef"] = tags.get("GPS GPSLongitudeRef", "E")
        return {"GPSInfo": gps_info} if gps_info else {}
    except Exception:
        return {}

def convert_to_degrees(value):
    try:
        d, m, s = value
        return d[0]/d[1] + (m[0]/m[1])/60 + (s[0]/s[1])/3600
    except Exception:
        return None

def get_coordinates(gps_info):
    lat = lon = None
    if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
        lat = convert_to_degrees(gps_info["GPSLatitude"])
        if gps_info["GPSLatitudeRef"] != "N":
            lat = -lat
    if "GPSLongitude" in gps_info and "GPSLongitudeRef" in gps_info:
        lon = convert_to_degrees(gps_info["GPSLongitude"])
        if gps_info["GPSLongitudeRef"] != "E":
            lon = -lon
    return lat, lon

def open_in_google_maps(lat, lon):
    url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    webbrowser.open(url)
    print(f"Opened Google Maps at: {url}")

# ---------- Download Images ----------
def download_images_from_page(url, folder_path):
    os.makedirs(folder_path, exist_ok=True)
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    img_tags = soup.find_all("img")

    downloaded_files = []
    for img in img_tags:
        img_url = img.get("src")
        if not img_url:
            continue
        img_url = urljoin(url, img_url)
        filename = os.path.basename(img_url)

        # ✅ Only keep filenames that look like phone/WhatsApp/camera photos
        if not re.match(r"(IMG[-_]\d{8}[-_]WA\d+\.jpg)|(IMG[_-]\d+\.jpg)|(DSC_\d+\.jpg)", filename, re.IGNORECASE):
            continue  # skip logos, icons, etc.

        save_path = os.path.join(folder_path, filename)
        try:
            img_data = requests.get(img_url).content
            with open(save_path, "wb") as f:
                f.write(img_data)
            downloaded_files.append(save_path)
            print(f"Downloaded: {save_path}")
        except Exception as e:
            print(f"Failed to download {img_url}: {e}")
    return downloaded_files

# ---------- Scan Folder ----------
def scan_folder(folder_path):
    supported_ext = (".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp")
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(supported_ext):
            image_path = os.path.join(folder_path, filename)
            print(f"\nScanning: {filename}")

            exif = extract_exif_pillow(image_path)
            if not exif or "GPSInfo" not in exif:
                exif = extract_exif_exifread(image_path)

            if "GPSInfo" in exif and exif["GPSInfo"]:
                lat, lon = get_coordinates(exif["GPSInfo"])
                if lat and lon:
                    print(f"Coordinates found: {lat}, {lon}")
                    open_in_google_maps(lat, lon)
                else:
                    print(f"No usable GPS coordinates in {filename}")
            else:
                print(f"No GPS data found in {filename}")

# ---------- Example Usage ----------
page_url = "https://isograft.com/boarding-houses-near/Cavendish%20University%20Zambia/Cavendish%20Medical%20Campus"  # replace with your URL
folder_path = "C:/Users/lweendo/project/baodinghouse/CUZ/images"

download_images_from_page(page_url, folder_path)
scan_folder(folder_path)
