import flask
from datetime import datetime, timedelta
import html
import pytz
import requests
from nyct_gtfs.feed import NYCTFeed
from requests.adapters import HTTPAdapter, Retry
from letterboxdpy import user as letterboxduser
import redis
import json

app = flask.Flask(__name__)

# LOCAL REDIS BACKUP FOR TESTING
# app.config['REDIS_URL'] = "redis://localhost:6379/0"

# EXTERNAL URL FOR TESTING LOCALLY
# app.config['REDIS_URL'] = 'rediss://red-d4udg92li9vc73d3dq5g:UV1ExfzjfZPgLJeE1J307BlwhdC3HyUz@virginia-keyvalue.render.com:6379'

# INTERNAL URL FOR DEPLOYMENT
app.config['REDIS_URL'] = 'redis://red-d4udg92li9vc73d3dq5g:6379'
redis_client = redis.from_url(app.config['REDIS_URL'])

# TODO: add daily / half hourly cache refresh cron jobs on screenings and news
# TODO: add Bluesky trending topics endpoint, get top stories in US, Ireland, and Globally
# TODO: add Wikipedia scraper endpoint, wiki article of the day / this day in history
# TODO: add Bandsintown scraper, index against digitized music pref catalogue
# TODO: add Moby-Dick API reader, do something fun with it
# TODO: add Gizz Tapes RSS reader, alert to new shows posted
# TODO: add PSN + NSO + Steam scraper, get last two weeks of activity
# TODO: add Letterboxd last two weeks of activity
# TODO: add signs of life endpoint that returns two weeks of game activity + letterboxd activity, 
#       date of last bluesky post, date of last update to the site

# TODO: add heartbeat on cron-job.org (here or below)
@app.route('/')
def kpi_ok():
    return 'KPI OK!'

# TODO: add heartbeat on cron-job.org (here or above)
@app.route('/health-check')
def health_check():
    return '', 200

def get_cached_result(key, refresh_only=False):
    if key == 'trains':
        # check if key exists with timestamp of -1 minute
        # if not, get fresh query
        time = datetime.now() - timedelta(minutes=1)
        datestring = time.strftime('%Y-%m-%d %H:%M')
        readable_datestring = time.strftime('%d/%m/%Y %H:%M')
        minutewise_trains_key = f'{key}_{datestring}'
        cached_result = redis_client.get(minutewise_trains_key)
        if cached_result is None:
            for expired_key in redis_client.scan_iter(f'{key}_*'):
                redis_client.delete(expired_key)
            new_result = get_trains().json
            new_result_bytes = json.dumps(new_result).encode('utf-8')
            redis_client.set(minutewise_trains_key, new_result_bytes)
        else:
            cached_result = json.loads(cached_result.decode('utf-8'))
    elif key == 'screenings':
        # check if key exists with timestamp of current day
        # if not, get fresh query
        datestring = datetime.now().strftime('%Y-%m-%d')
        readable_datestring = datetime.now().strftime('%d/%m/%Y')
        daily_screenings_key = f'{key}_{datestring}'
        cached_result = redis_client.get(daily_screenings_key)
        if cached_result is None:
            for expired_key in redis_client.scan_iter(f'{key}_*'):
                redis_client.delete(expired_key)
            new_result = get_screenings().json
            new_result_bytes = json.dumps(new_result).encode('utf-8')
            redis_client.set(daily_screenings_key, new_result_bytes)
        else:
            cached_result = json.loads(cached_result.decode('utf-8'))
    elif key == 'hacker-news':
        # check if key exists from top of hour
        # TODO: make more clever solution to always get most recent half hour, compare minute vals
        # if not, get fresh query
        time = datetime.now().replace(minute=0)
        datestring = time.strftime('%Y-%m-%d %H:%M')
        readable_datestring = time.strftime('%d/%m/%Y %H:%M')

        hourly_hacker_news_key = f'{key}_{datestring}'
        cached_result = redis_client.get(hourly_hacker_news_key)
        if cached_result is None:
            for expired_key in redis_client.scan_iter(f'{key}_*'):
                redis_client.delete(expired_key)
            new_result = get_hacker_news().json
            new_result_bytes = json.dumps(new_result).encode('utf-8')
            redis_client.set(hourly_hacker_news_key, new_result_bytes)
        else:
            cached_result = json.loads(cached_result.decode('utf-8'))

    if not refresh_only:
        result = cached_result or new_result
        response = {
            'last_updated': readable_datestring,
            'result': result
        }
        response = flask.jsonify(response)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    else:
        return 'Refresh OK', 200

@app.route('/kpi/trains')
def get_trains_from_cache_or_live():
    return get_cached_result('trains')

@app.route('/kpi/screenings')
def get_screenings_from_cache_or_live():
    return get_cached_result('screenings')

@app.route('/kpi/hacker-news')
def get_hacker_news_from_cache_or_live():
    return get_cached_result('hacker-news')

# TODO: add daily refresh job on cron-job.org
@app.route('/kpi/screenings/refresh')
def refresh_screenings():
    return get_cached_result('screenings', refresh_only=True)

# TODO: add hourly refresh job on cron-job.org
@app.route('/kpi/hacker-news/refresh')
def refresh_hacker_news():
    return get_cached_result('hacker-news', refresh_only=True)

# TODO: DRY out inner methods below repeating daily data insertion
# TODO: Import static LIRR data
# TODO: Construct set of West/East Port Washington trains from Penn, Woodside, Bayside
# TODO: Account for transfers at woodside ^
# TODO: Construct set of West/East Atlantic Terminal <-> Jamaica Trains
# TODO: Construct set of trips connecting 2/3 from GAP to Penn then LIRR to Bayside
# TODO: Construct set of trips connecting 2/3 from GAP to Barclays then LIRR to Jamaica
# TODO: Create graphs of commutes to the above plus movie theaters along different lines
# TODO: Add projected commute times onto metadata of listings in /screenings endpoint
def get_trains():
    output = {
        'N-23': {
            'trips': [],
            'trains_stopping_at_grand_army': False,
            'trains_stopping_at_wall_street': False,
            'trains_stopping_at_penn_station': False,
            'trains_stopping_at_lincoln_center': False
        },
        'S-23': {
            'trips': [],
            'trains_stopping_at_grand_army': False,
            'trains_stopping_at_penn_station': False,
            'trains_stopping_at_wall_street': False,
            'trains_stopping_at_lincoln_center': False
        },
        'N-Q': {
            'trips': [],
        },
        'S-Q': {
            'trips': [],
        }
    }

    feed_1_2_3 = NYCTFeed("2")
    sorted_trips = sorted(feed_1_2_3.trips, key=lambda trip: trip.stop_time_updates[-1].arrival)
    for trip in sorted_trips:
        # pre-sorting
        # for trip in feed_1_2_3.trips:
        input = {
            "summary": str(trip)
        }
        if trip.route_id not in ['1', '4', '5', '6', '7', 'GS']:
            input['route_id'] = trip.route_id
            stop_time_updates = trip.stop_time_updates
            for update in stop_time_updates:
                if update.arrival is not None:
                    arrival_gmt = update.arrival
                    est = pytz.timezone('US/Eastern')
                    arrival_est = datetime(arrival_gmt.year, arrival_gmt.month, arrival_gmt.day, arrival_gmt.hour, arrival_gmt.minute, arrival_gmt.second, tzinfo=est)
                    arrival_est = arrival_est - timedelta(hours=5)
                    arrival_est = arrival_est.strftime('%H:%M')
                else:
                    arrival_est = "-"
                if update.stop_name == 'Grand Army Plaza':
                    input['grand_army_arrival'] = arrival_est
                    output[f'{trip.direction}-23']['trains_stopping_at_grand_army'] = True
                elif update.stop_name == 'Wall St':
                    input['wall_street_arrival'] = arrival_est
                    output[f'{trip.direction}-23']['trains_stopping_at_wall_street'] = True
                elif update.stop_name == '34 St-Penn Station':
                    input['penn_station_arrival'] = arrival_est
                    output[f'{trip.direction}-23']['trains_stopping_at_penn_station'] = True

            output[f'{trip.direction}-23']['trips'].append(input)
    feed_q = NYCTFeed("Q")
    sorted_trips = sorted(feed_q.trips, key=lambda trip: trip.departure_time)
    for trip in sorted_trips:
        input = {
            "summary": str(trip)
        }
        if trip.route_id == 'Q':
            input['route_id'] = trip.route_id
            stop_time_updates = trip.stop_time_updates
            for update in stop_time_updates:
                if update.arrival is not None:
                    arrival_gmt = update.arrival
                    est = pytz.timezone('US/Eastern')
                    arrival_est = datetime(arrival_gmt.year, arrival_gmt.month, arrival_gmt.day, arrival_gmt.hour, arrival_gmt.minute, arrival_gmt.second, tzinfo=est)
                    arrival_est = arrival_est - timedelta(hours=5)
                    arrival_est = arrival_est.strftime('%H:%M')
                else:
                    arrival_est = "-"
                if update.stop_name == '7 Av':
                    input['seventh_av_arrival'] = arrival_est
                elif update.stop_name == '14 St-Union Sq':
                    input['union_square_arrival'] = arrival_est
                elif update.stop_name == 'Times Sq-42 St':
                    input['times_square_arrival'] = arrival_est 

            output[f'{trip.direction}-Q']['trips'].append(input)

    response = flask.jsonify(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

# TODO: de-dupe some screenings in favor of the one with more metadata
def get_screenings():
    highlight_movies = []
    lb_user = letterboxduser.User('flynncredible')
    lb_diary_entries = lb_user.get_diary()['entries']
    for key in lb_diary_entries.keys():
        entry = lb_diary_entries[key]
        if entry['name'] not in highlight_movies:
            highlight_movies.append(entry['name'])
    lb_watchlist = lb_user.get_watchlist()['data']
    for key in lb_watchlist.keys():
        movie = lb_watchlist[key]
        if movie['name'] not in highlight_movies:
            highlight_movies.append(movie['name'])

    output = []
    screening_data = {}
    day = datetime.today()

    # TODO: DRY this out with helper
    # First day, idk why it has to be separate - TODO: fix later
    daystring = day.strftime('%Y%m%d')
    screenings = requests.get(f'https://www.screenslate.com/api/screenings/date?_format=json&date={daystring}&field_city_target_id=10969').json()
    nids = ""
    for screening in screenings:
        nid = screening['nid']
        screening_data[nid] = {
            'start_time': screening['field_time'],
            'note': screening['field_note']
        }
        nids += f'{nid}+'
    nids = nids[:-1]
    screening_details = requests.get(f'https://www.screenslate.com/api/screenings/id/{nids}?_format=json').json()
    day_summary = {
        'day': day.strftime('%A, %B %-d'),
        'screenings': []
    }
    for detail in screening_details:
        stripped_title = detail['media_title_labels'].split('>')
        if len(stripped_title) == 1:
            clean_title = stripped_title[0]
        else:
            clean_title = stripped_title[1].split('<')[0]
        if clean_title == '' or clean_title == None:
            clean_title = detail['title']
        
        stripped_venue_title = detail['venue_title'].split('>')
        if len(stripped_venue_title) == 1:
            clean_venue_title = stripped_venue_title[0]
        else:
            clean_venue_title = stripped_venue_title[1].split('<')[0]

        if len(detail['media_title_info'].split('<span>')) >= 4:
            stripped_director = detail['media_title_info'].split('<span>')[1].split('</span>')[0].replace('\\n','')
            stripped_year = detail['media_title_info'].split('<span>')[2].split('</span>')[0]
            stripped_runtime = detail['media_title_info'].split('<span>')[3].split('</span>')[0]
            stripped_format = detail['media_title_info'].split('<span>')[-1].split('</span>')[0]
            title_info = detail['media_title_info']
            if stripped_format == stripped_runtime or stripped_format == stripped_year:
                stripped_format = '-'
        else:
            stripped_director = '-'
            stripped_year = '-'
            stripped_runtime = '-'
            stripped_format = '-'
            

        day_summary['screenings'].append(
            {
                'title': html.unescape(clean_title.strip()),
                'director': html.unescape(stripped_director.strip()),
                'venue_title': html.unescape(clean_venue_title.strip()),
                'format': detail['media_title_format'] or stripped_format,
                'link': detail['field_url'],
                'start_time': screening_data[detail['nid']]['start_time'],
                'run_time': stripped_runtime,
                'year': stripped_year,
                'note': html.unescape(screening_data[detail['nid']]['note']),
                'highlight': html.unescape(clean_title.strip()) in highlight_movies
            }
        )
        sorted_screenings = sorted(day_summary['screenings'], key=lambda screening: datetime.strptime(screening['start_time'], '%H:%M''%p') if ':' in screening['start_time'] else datetime.strptime(screening['start_time'], '%H''%p'))
        day_summary['screenings'] = sorted_screenings
    output.append(day_summary)

    for x in range(4):
        day = day + timedelta(days=1)
        daystring = day.strftime('%Y%m%d')
        screenings = requests.get(f'https://www.screenslate.com/api/screenings/date?_format=json&date={daystring}&field_city_target_id=10969').json()
        nids = ""
        for screening in screenings:
            nid = screening['nid']
            screening_data[nid] = {
                'start_time': screening['field_time'],
                'note': screening['field_note']
            }
            nids += f'{nid}+'
        nids = nids[:-1]
        screening_details = requests.get(f'https://www.screenslate.com/api/screenings/id/{nids}?_format=json').json()
        day_summary = {
            'day': day.strftime('%A, %B %-d'),
            'screenings': []
        }
        for detail in screening_details:
            stripped_title = detail['media_title_labels'].split('>')
            if len(stripped_title) == 1:
                clean_title = stripped_title[0]
            else:
                clean_title = stripped_title[1].split('<')[0]
            if clean_title == '' or clean_title == None:
                clean_title = detail['title']
            
            stripped_venue_title = detail['venue_title'].split('>')
            if len(stripped_venue_title) == 1:
                clean_venue_title = stripped_venue_title[0]
            else:
                clean_venue_title = stripped_venue_title[1].split('<')[0]

            if len(detail['media_title_info'].split('<span>')) >= 4:
                stripped_director = detail['media_title_info'].split('<span>')[1].split('</span>')[0].replace('\\n','')
                stripped_year = detail['media_title_info'].split('<span>')[2].split('</span>')[0]
                stripped_runtime = detail['media_title_info'].split('<span>')[3].split('</span>')[0]
                stripped_format = detail['media_title_info'].split('<span>')[-1].split('</span>')[0]
                title_info = detail['media_title_info']
                if stripped_format == stripped_runtime or stripped_format == stripped_year:
                    stripped_format = '-'
            else:
                stripped_director = '-'
                stripped_year = '-'
                stripped_runtime = '-'
                stripped_format = '-'
                

            day_summary['screenings'].append(
                {
                    'title': html.unescape(clean_title.strip()),
                    'director': html.unescape(stripped_director.strip()),
                    'venue_title': html.unescape(clean_venue_title.strip()),
                    'format': detail['media_title_format'] or stripped_format,
                    'link': detail['field_url'],
                    'start_time': screening_data[detail['nid']]['start_time'],
                    'run_time': stripped_runtime,
                    'year': stripped_year,
                    'note': html.unescape(screening_data[detail['nid']]['note']),
                    'highlight': html.unescape(clean_title.strip()) in highlight_movies
                }
            )
            sorted_screenings = sorted(day_summary['screenings'], key=lambda screening: datetime.strptime(screening['start_time'], '%H:%M''%p') if ':' in screening['start_time'] else datetime.strptime(screening['start_time'], '%H''%p'))
            day_summary['screenings'] = sorted_screenings
        output.append(day_summary)

    response = flask.jsonify(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

# TODO: Allow loading of subsequent pages / add timestamps / comments / other metadata?
def get_hacker_news():
    s = requests.Session()
    retries = Retry(total=5,
                backoff_factor=0.1,
                status_forcelist=[ 500, 502, 503, 504 ])
    s.mount('https://', HTTPAdapter(max_retries=retries))

    output = []
    top_stories = s.get('https://hacker-news.firebaseio.com/v0/topstories.json').json()
    limit = 25
    count = 0
    for story in top_stories:
        if count < limit:
            story_data = s.get(f'https://hacker-news.firebaseio.com/v0/item/{story}.json').json()
            if story_data['type'] == 'job':
                continue
            score = story_data['score']
            if score < 250:
                continue
            title = story_data['title']
            url = story_data['url'] if 'url' in story_data.keys() else None
            comments = story_data['descendants']
            shortened_url = url if url == None else story_data['url'].split('/')[2].replace('www.','')
            output.append(
                {
                    'title': title,
                    'url': url,
                    'shortened_url': f'({shortened_url})',
                    'comments_link': f'https://news.ycombinator.com/item?id={story}',
                    'score': score,
                    'comments': comments
                }
            )
            count += 1
    response = flask.jsonify(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

# TODO: auth bearer token grabbing
# TODO: secret handling to get bearer token (research in Render)
# @app.route('/kpi/wiki')
# def get_wiki_news():
#     today = datetime.now()
#     date = today.strftime('%Y/%m/%d')
#     language_code = 'en' # English

#     headers = {
#     'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
#     'User-Agent': 'kpi (kevin.flynn@hey.com)'
#     }

#     base_url = 'https://api.wikimedia.org/feed/v1/wikipedia/'
#     url = base_url + language_code + '/featured/' + date
#     response = requests.get(url, headers=headers)