import requests
import re
import yaml
import logging
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    '-d', '--debug',
    help="Print lots of debugging statements",
    action="store_const", dest="loglevel", const=logging.DEBUG,
    default=logging.INFO,
)
parser.add_argument(
    '--all-movies', 
    help="Process all movies, including unmonitored ones",
    action="store_true"
)
args = parser.parse_args()    
logging.basicConfig(level=args.loglevel, filename='elsewherr.log', filemode='w', format='%(asctime)s :: %(levelname)s :: %(message)s')

logging.debug('DEBUG Logging Enabled')
logging.debug('Loading Config and setting the list of required Providers')
config = yaml.safe_load(open("config.yaml"))
requiredProvidersLower = [re.sub('[^A-Za-z0-9]+', '', x).lower() for x in config["requiredProviders"]]
logging.debug(f'requiredProvidersLower: {requiredProvidersLower}')

# Request Headers
radarrHeaders = {'Content-Type': 'application/json', "X-Api-Key":config["radarrApiKey"]}
tmdbHeaders = {'Content-Type': 'application/json'}

# Create all Tags for Providers
logging.debug('Create all Tags for Providers within Radarr')
print("🏷️  Setting up provider tags in Radarr...")
for requiredProvider in config["requiredProviders"]:
    providerTag = (config["tagPrefix"] + re.sub('[^A-Za-z0-9]+', '', requiredProvider)).lower()
    newTagJson = {
            'label': providerTag,
            'id': 0
        }
    logging.debug(f'newTagJson: {newTagJson}')
    radarrTagsPost = requests.post(config["radarrUrl"]+'/api/v3/tag', json=newTagJson, headers=radarrHeaders)
    logging.debug(f'radarrTagsPost Response Status: {radarrTagsPost.status_code}')
    
    # Tag creation can return 201 (created) or 400 (already exists), both are fine
    if radarrTagsPost.status_code in [201, 400]:
        logging.debug(f'Tag "{providerTag}" handled successfully')
    else:
        logging.warning(f'Unexpected response for tag creation: {radarrTagsPost.status_code}')

# Get all Tags and create lists of those to remove and add
logging.debug('Get all Tags and create lists of those to remove and add')
radarrTagsGet = requests.get(config["radarrUrl"]+'/api/v3/tag', headers=radarrHeaders)
if radarrTagsGet.status_code != 200:
    print(f"❌ Failed to retrieve tags from Radarr. Status code: {radarrTagsGet.status_code}")
    sys.exit(1)

logging.debug(f'radarrTagsGet Response Status: {radarrTagsGet.status_code}')
existingTags = radarrTagsGet.json()
logging.debug(f'existingTags: {existingTags}')
providerTagsToRemove = []
providerTagsToAdd = []

for existingTag in existingTags:
    if config["tagPrefix"].lower() in existingTag["label"]:
        logging.debug(f'Adding tag [{existingTag}] to the list of tags to be removed')
        providerTagsToRemove.append(existingTag)
    if str(existingTag["label"]).replace(config["tagPrefix"].lower(), '') in requiredProvidersLower:
        logging.debug(f'Adding tag [{existingTag}] to the list of tags to be added')
        providerTagsToAdd.append(existingTag)

# Get all Movies from Radarr
logging.debug('Getting all Movies from Radarr')
print("🎬 Retrieving movie list from Radarr...")
radarrResponse = requests.get(config["radarrUrl"]+'/api/v3/movie', headers=radarrHeaders)
if radarrResponse.status_code != 200:
    print(f"❌ Failed to retrieve movies from Radarr. Status code: {radarrResponse.status_code}")
    print(f"Response: {radarrResponse.text}")
    sys.exit(1)

logging.debug(f'radarrResponse Status: {radarrResponse.status_code}')
all_movies = radarrResponse.json()
logging.debug(f'Total Number of Movies in Radarr: {len(all_movies)}')

# Filter for only monitored movies (unless --all-movies flag is used)
if args.all_movies:
    movies = all_movies
    print(f"📊 Processing all {len(all_movies)} movies in Radarr (including unmonitored)")
else:
    movies = [movie for movie in all_movies if movie.get('monitored', False)]
    monitored_count = len(movies)
    unmonitored_count = len(all_movies) - monitored_count

    logging.debug(f'Monitored Movies: {monitored_count}')
    logging.debug(f'Unmonitored Movies: {unmonitored_count}')
    print(f"📊 Found {len(all_movies)} total movies in Radarr")
    print(f"   ✅ {monitored_count} monitored movies (will be processed)")
    print(f"   ⏸️  {unmonitored_count} unmonitored movies (will be skipped)")
    print("   💡 Use --all-movies to process unmonitored movies too")

# Work on each movie
logging.debug('Working on selected movies')
total_movies = len(movies)
if total_movies == 0:
    print("\n⚠️  No movies found to process. Exiting.")
    sys.exit(0)

movie_type = "all" if args.all_movies else "monitored"
print(f"\n🎬 Processing {total_movies} {movie_type} movies...")
print("=" * 80)

for movie_index, movie in enumerate(movies, 1):
    update = movie
    #time.sleep(1)
    
    # Calculate and display progress
    progress_percent = (movie_index / total_movies) * 100
    
    # Terminal progress output
    monitor_status = "✅ Monitored" if movie.get('monitored', False) else "⏸️  Unmonitored"
    print(f"\n[{movie_index}/{total_movies}] ({progress_percent:.1f}%) Processing: {movie['title']}")
    print(f"TMDB ID: {movie['tmdbId']} | {monitor_status}")
    
    logging.info("-------------------------------------------------------------------------------------------------")
    logging.info(f"Movie {movie_index}/{total_movies}: "+movie["title"])
    logging.info("TMDB ID: "+str(movie["tmdbId"]))
    logging.debug(f'Movie record from Radarr: {movie}')

    logging.debug("Getting the available providers for: "+movie["title"])
    print("  📡 Fetching providers from TMDB...")
    tmdbResponse = requests.get('https://api.themoviedb.org/3/movie/'+str(movie["tmdbId"])+'/watch/providers?api_key='+config["tmdbApiKey"], headers=tmdbHeaders)
    logging.debug(f'tmdbResponse Response: {tmdbResponse}')
    
    # Check if the TMDB API response is successful
    if tmdbResponse.status_code != 200:
        print(f"  ❌ TMDB API request failed with status code: {tmdbResponse.status_code}")
        logging.error(f"TMDB API request failed with status code: {tmdbResponse.status_code}")
        logging.error(f"Response content: {tmdbResponse.text}")
        continue
    
    tmdbProviders = tmdbResponse.json()
    logging.debug(f'tmdbProviders JSON: {tmdbProviders}')
    
    # Check if 'results' key exists in the response
    if "results" not in tmdbProviders:
        print(f"  ❌ No provider results found for {movie['title']}")
        logging.error(f"No 'results' key in TMDB response for movie: {movie['title']}")
        logging.error(f"TMDB response: {tmdbProviders}")
        continue
    
    logging.debug(f'Total Providers: {len(tmdbProviders["results"])}')

    # Check that flatrate providers exist for the chosen region
    logging.debug("Check that flatrate providers exist for the chosen region")
    try:
        providers = tmdbProviders["results"][config["providerRegion"]]["flatrate"]
        print(f"  ✅ Found {len(providers)} streaming provider(s)")
        logging.debug(f'Flat Rate Providers: {providers}')
    except KeyError:
        print("  ⚠️  No streaming providers available")
        logging.info("No Flatrate Providers")
        continue

    # Remove all provider tags from movie
    logging.debug("Remove all provider tags from movie")
    print("  🏷️  Updating tags...")
    updateTags = movie.get("tags", [])
    logging.debug(f'updateTags - Start: {updateTags}')
    tags_removed = 0
    for providerIdToRemove in (providerIdsToRemove["id"] for providerIdsToRemove in providerTagsToRemove):
        try:
            updateTags.remove(providerIdToRemove)
            tags_removed += 1
            logging.debug(f'Removing providerId: {providerIdToRemove}')
        except ValueError:
            # Tag was not in the list, which is fine
            continue

    # Add all required providers
    logging.debug("Adding all provider tags to movie")
    tags_added = 0
    provider_names = []
    for provider in providers:
        providerName = provider["provider_name"]
        provider_names.append(providerName)
        tagToAdd = (config["tagPrefix"] + re.sub('[^A-Za-z0-9]+', '', providerName)).lower()
        for providerTagToAdd in providerTagsToAdd:
            if tagToAdd in providerTagToAdd["label"]:
                logging.info("Adding tag "+tagToAdd)
                updateTags.append(providerTagToAdd["id"])
                tags_added += 1

    print(f"  📝 Removed {tags_removed} old tag(s), added {tags_added} new tag(s)")
    if provider_names:
        print(f"  🎯 Providers: {', '.join(provider_names)}")

    logging.debug(f'updateTags - End: {updateTags}')
    update["tags"] = updateTags
    logging.debug(f'Updated Movie record to send to Radarr: {update}')

    # Update movie in Radarr
    print("  💾 Updating movie in Radarr...")
    radarrUpdate = requests.put(config["radarrUrl"]+'/api/v3/movie', json=update, headers=radarrHeaders)
    
    # Check for successful status codes (200-299 range)
    if 200 <= radarrUpdate.status_code < 300:
        status_messages = {
            200: "✅ Successfully updated!",
            201: "✅ Successfully created!",
            202: "✅ Update accepted (processing)!",
            204: "✅ Update completed!"
        }
        message = status_messages.get(radarrUpdate.status_code, f"✅ Success (code: {radarrUpdate.status_code})!")
        print(f"  {message}")
    else:
        print(f"  ❌ Update failed with status code: {radarrUpdate.status_code}")
        if radarrUpdate.text:
            logging.error(f"Error response: {radarrUpdate.text}")
    
    logging.info(f"Radarr update response - Status: {radarrUpdate.status_code}, Response: {radarrUpdate.text}")

# Final summary
print("\n" + "=" * 80)
print(f"🎉 Processing complete! Processed {total_movies} movies.")
print("=" * 80)
    
