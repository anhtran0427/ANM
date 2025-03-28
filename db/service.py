import uuid 
urls=[]

def get_urls():
	global urls
	return urls

def clear_urls():
    global urls
    urls=[]

def get_url(id):
    global urls
    print(urls)
    print("service get url")
    for url in urls:
        if url['Id'] == id:
            return url
    return None

def add_url(url, status):
	global urls
	url = {
		'Id': str(uuid.uuid4()),
		'URL': url,
		'Status': status,
	}
	urls.insert(0, url)
	return url

def update_url(id, URL, status):
  global urls
  for url in urls:
    if url['Id'] == id:
      url['URL'] = URL if URL else url['URL']
      url['Status'] = status
      return url
  return None

def clear_url(id):
  global urls
  for ind in range(len(urls)):
    if ind not in range(len(urls)):
        break
    if urls[ind]['Id'] == id:
      urls.pop(ind)

def clear_url_by_name(URL):
  global urls
  print(len(urls))
  print(urls)
  for ind in range(len(urls)):
    if ind not in range(len(urls)):
        break
    if urls[ind]['URL'] == URL:
      urls.pop(ind)

def get_url_by_name(URL):
    global urls
    for url in urls:
        if url['URL'] == URL:
            return url
    return None
