import flask
from datetime import datetime, timedelta
import html
import pytz
import requests
from nyct_gtfs.feed import NYCTFeed

app = flask.Flask(__name__)

@app.route('/kpi/hello')
def hello_world():
    return 'Hello, World!'

@app.route('/kpi/trains')
def get_trains():
    output = {
        'debug': len(NYCTFeed("2").trips),
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
# TODO: sort by start time (daily)
@app.route('/kpi/screenings')
def get_screenings():
    output = []
    screening_data = {}
    day = datetime.today()
    for x in range(8):
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
                    'note': html.unescape(screening_data[detail['nid']]['note'])
                }
            )
        output.append(day_summary)

    response = flask.jsonify(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response