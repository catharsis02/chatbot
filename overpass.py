

try:
	import overpy           # optional: used by some helper functions
except Exception:
	overpy = None
try:
	import pandas as pd     # optional: used by CLI CSV export helpers
except Exception:
	pd = None
import json 						# to import json
import requests					# to import requests
from cache import ttl_cache
import math



#this function gets the input from user.  INPUT = {laitutde, longitude, search_radius, option to specify the data domain like hospital,education etc.}
def get_input():
	print("\nEnter latitude (example->'28.584569') >> ")
	latitude = input()
	print("\nEnter longitude (example->'77.215868') >> ")
	longitude = input()
	print("\nEnter scan radius for target.(in meters) (EXAMPLE->'20000') >> ")
	search_radius = input()
	print("\nEnter an option.(integer) :\n1. Hospitals Data\n2. Schools Data\n3. Road Network Data\n4. terrains Data(it may don't work for large radius)\n5. Electricity Network Data")
	option = int(input("\n>>>"))
	while option not in [1,2,3,4,5]: 
		print("Invalid Option. Try Again \n>>")
		option = int(input())
	return([latitude,longitude,search_radius,option])   #returns the list of user inputs



#this function arrenge user inputs to build the 'query'(in overpass QL language)  for hospitals data and returns the query
def get_hospital_query(user_input):
	prefix = """[out:json][timeout:50];(node["amenity"="hospital"](around:""" #this is string of syntex in 'Overpass QL' language
	suffix = """););out body;>;out skel qt;"""							      #this is string of syntex in 'Overpass QL' language
	q = user_input[2]+','+user_input[0]+','+user_input[1]       #(radius,latitude,longitude) in a string from the user input
	built_query = prefix + q + suffix                           #arrange all above strings into a correct order to form complete query
	return built_query 														              #return the complete query to main function



#this function arrenge user inputs to build the 'query'(in overpass QL language) for schools,college,university and returns the query
def get_school_query(user_input):
	prefix = """[out:json][timeout:50];("""  				          	#this is string of syntex in 'Overpass QL' language
	schoolnode="""node["amenity"="school"](around:""" 		  	  #this is string of syntex in 'Overpass QL' language
	collegenode="""node["amenity"="college"](around:"""		  	  #this is string of syntex in 'Overpass QL' language
	universitynode = """node["amenity"="university"](around:""" #this is string of syntex in 'Overpass QL' language
	suffix = """);out body;>;out skel qt;"""				        	  #this is string of syntex in 'Overpass QL' language
	q = user_input[2]+','+user_input[0]+','+user_input[1]    	  #(radius,latitude,longitude) in a string form the user input
	built_query = prefix + schoolnode+ q +');'+ collegenode+ q +');' + universitynode+ q+');'+ suffix  #combine all the above strings in correct order to form a query
	return built_query											                    #returns the complete overpass query



#this function arrenge user inputs to build the 'query' (in overpass QL language) for roads data and returns the query
def get_roads_query(user_input):
	prefix = """[out:json][timeout:50];(way["highway"](around:""" #this is string of syntex in 'Overpass QL' language
	suffix = """););out body;"""							   	  #this is string of syntex in 'Overpass QL' language
	q = user_input[2]+','+user_input[0]+','+user_input[1]         #(radius,latitude,longitude) in a string from the user input
	built_query = prefix + q + suffix                             #arrange all above strings into a correct order to form complete query
	return built_query                                            #return the built query further



#this function arrenge user inputs to build the 'query' (in overpass QL language) for all data and returns the query
def get_terrian_query(user_input):
	prefix = """[out:json][timeout:50];("""  				          	#this is string of syntex in 'Overpass QL' language
	schoolnode="""node(around:""" 		  	 										  #this is string of syntex in 'Overpass QL' language
	collegenode="""relation(around:"""		  	  								#this is string of syntex in 'Overpass QL' language
	universitynode = """way(around:""" 													#this is string of syntex in 'Overpass QL' language
	suffix = """);out body;>;out skel qt;"""				        	  #this is string of syntex in 'Overpass QL' language
	q = user_input[2]+','+user_input[0]+','+user_input[1]    	  #(radius,latitude,longitude) in a string form the user input
	built_query = prefix + schoolnode+ q +');'+ collegenode+ q +');' + universitynode+ q+');'+ suffix  #combine all the above strings in correct order to form a query
	print(built_query)
	return built_query



#this function arrenge user inputs to build the 'query' (in overpass QL language) for electricity data and returns the query
def get_electricity_query(user_input):
	prefix = """[out:json][timeout:50];(node[power](around:""" 		#this is string of syntex in 'Overpass QL' language
	suffix = """););out body;>;out skel qt;"""							   	  #this is string of syntex in 'Overpass QL' language
	q = user_input[2]+','+user_input[0]+','+user_input[1]         #(radius,latitude,longitude) in a string from the user input
	built_query = prefix + q + suffix                             #arrange all above strings into a correct order to form complete query
	return built_query


# this funciton uses the overpy.Overpass API to send a query and get the response from overpass servers in json format and then it extract the nodes(hospitals , schools) data to a csv file.
def extract_nodes_data_from_OSM(built_query):
	if pd is None:
		raise RuntimeError('pandas is required for extract_nodes_data_from_OSM; install pandas or call search_pois instead')
	api = overpy.Overpass()                       # creating a overpass API instance 
	result = api.query(built_query)               # get result from API by sending the query to overpass servers
	list_of_node_tags = []                        # initializing empty list , we'll use it to form a dataframe .
	for node in result.nodes:                     # from each node , get the all tags information
		node.tags['latitude'] =  node.lat
		node.tags['longitude'] = node.lon
		node.tags['id'] = node.id
		list_of_node_tags.append(node.tags)
	data_frame = pd.DataFrame(list_of_node_tags)  # forming a pandas dataframe using list of dictionaries
	data_frame.to_csv('output_data.csv')
	print("\nCSV file created- 'output_data.csv'. Check the file in current directory.")
	return data_frame                             # return data frame if you want to use it further in main function.



# this function only extracts the raw  json data from overpass api through get request
def extract_raw_data_from_OSM(built_query):
	overpass_url = "http://overpass-api.de/api/interpreter" 					 #url of overpass api
	response = requests.get(overpass_url,params={'data': built_query}) # sending a get request and passing the overpass query as data parameter in url
	print(response.text)
	json_data = response.json()
	with open("output_data.json", "w") as outfile:  									 # writing the json output to a file
		json.dump(json_data, outfile)
	print("Raw Data extraction successfull!  check 'output_data.json' file.")
	return json_data
 
	
	


if __name__ == '__main__':  #main function to act accordingly to the user's input.

	user_input=get_input()
	option = user_input[3]
	if(option==1):
		query = get_hospital_query(user_input)
		data_frame = extract_nodes_data_from_OSM(query)
	elif(option==2):
		query = get_school_query(user_input)
		data_frame = extract_nodes_data_from_OSM(query)
	elif(option==3):
		query = get_roads_query(user_input)
		data_frame = extract_raw_data_from_OSM(query)
	elif(option==4):
		query = get_terrian_query(user_input)
		data_frame = extract_raw_data_from_OSM(query)
	elif(option==5):
		query = get_electricity_query(user_input)
		data_frame= extract_nodes_data_from_OSM(query)
	print("Note: \n1. Please rename the output file, so that it can't be overwritten when you execute this program again.\n2. output file shouldn't remain open while running this program, because writing will perform on the output file while executing the program next time. ")



def _build_overpass_query(kind, lat, lon, radius_m=20000, limit=50):
	"""Return an Overpass QL query for the requested kind.

	kind: one of 'hospitals','schools','roads','electricity','all'
	"""
	# sanitize inputs
	try:
		lat_f = float(lat)
		lon_f = float(lon)
		radius_i = int(radius_m)
	except Exception:
		raise ValueError('Invalid lat/lon/radius')

	# Normalize some common plural/synonym forms
	k = (kind or '').lower()
	if k in ('hospital', 'hospitals'):
		q = f'[out:json][timeout:25];(node["amenity"="hospital"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('pharmacy', 'pharmacies'):
		q = f'[out:json][timeout:25];(node["amenity"="pharmacy"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('school', 'schools'):
		q = f'[out:json][timeout:25];(node["amenity"="school"](around:{radius_i},{lat_f},{lon_f});node["amenity"="college"](around:{radius_i},{lat_f},{lon_f});node["amenity"="university"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('fuel', 'petrol', 'gas', 'fuelstation'):
		q = f'[out:json][timeout:25];(node["amenity"="fuel"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('police',):
		q = f'[out:json][timeout:25];(node["amenity"="police"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('fire_station', 'firestation', 'fire-station'):
		q = f'[out:json][timeout:25];(node["amenity"="fire_station"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k == 'roads' or k == 'road' or k == 'highway':
		q = f'[out:json][timeout:25];(way["highway"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k in ('electricity', 'power'):
		q = f'[out:json][timeout:25];(node["power"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	elif k == 'amenity' or k == 'all' or k == 'node':
		# generic all nodes in area
		q = f'[out:json][timeout:25];(node(around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	else:
		# treat unknown kinds as amenity=k where possible (common cases)
		# fall back to filtering by amenity tag
		q = f'[out:json][timeout:25];(node["amenity"="{k}"](around:{radius_i},{lat_f},{lon_f}););out body;>;out skel qt;'
	return q


@ttl_cache(ttl_seconds=120)
def search_pois(lat, lon, radius_m=20000, kind='amenity', limit=100):
	"""Query Overpass API and return a list of POIs with lat/lon, name, type, tags.

	Results are cached for a short TTL to avoid repeated calls to Overpass for
	identical queries.
	"""
	q = _build_overpass_query(kind, lat, lon, radius_m=radius_m, limit=limit)
	overpass_url = 'http://overpass-api.de/api/interpreter'
	resp = requests.get(overpass_url, params={'data': q}, timeout=15)
	resp.raise_for_status()
	data = resp.json()
	elements = data.get('elements', []) if isinstance(data, dict) else []
	pois = []
	for el in elements:
		typ = el.get('type')
		lat_v = el.get('lat') or (el.get('center') and el.get('center').get('lat'))
		lon_v = el.get('lon') or (el.get('center') and el.get('center').get('lon'))
		tags = el.get('tags', {}) or {}
		name = tags.get('name') or tags.get('official_name') or tags.get('ref') or ''
		poi = {
			'id': el.get('id'),
			'osm_type': typ,
			'lat': float(lat_v) if lat_v else None,
			'lon': float(lon_v) if lon_v else None,
			'name': name,
			'tags': tags
		}
		if poi['lat'] and poi['lon']:
			pois.append(poi)
		if len(pois) >= limit:
			break

	# compute haversine distance (km) to sort nearest-first
	def _haversine(a_lat, a_lon, b_lat, b_lon):
		R = 6371.0
		phi1 = math.radians(a_lat)
		phi2 = math.radians(b_lat)
		dphi = math.radians(b_lat - a_lat)
		dlambda = math.radians(b_lon - a_lon)
		x = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2.0)**2
		return 2 * R * math.asin(min(1, math.sqrt(x)))

	for p in pois:
		try:
			p['distance_km'] = round(_haversine(float(lat), float(lon), float(p['lat']), float(p['lon'])), 3)
		except Exception:
			p['distance_km'] = None

	# sort by distance (None values go to the end)
	pois.sort(key=lambda x: (x['distance_km'] is None, x['distance_km']))

	# enforce limit after sorting
	if len(pois) > limit:
		pois = pois[:limit]

	return pois