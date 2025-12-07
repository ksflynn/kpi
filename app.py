import flask
import datetime
import pytz
from nyct_gtfs import NYCTFeed

app = flask.Flask(__name__)

@app.route('/kpi/hello')
def hello_world():
    return 'Hello, World!'

# TODO: provided time sorted list of northbound 2/3 trains, 
# in a grid with estimated times of arrival to both wall street, penn, and columbus
@app.route('/kpi/trains')
def get_trains():
    output = {
        'debug': len(NYCTFeed("2").trips),
        'N': {
            'trips': [],
            'trains_stopping_at_grand_army': False,
            'trains_stopping_at_wall_street': False,
            'trains_stopping_at_penn_station': False,
            'trains_stopping_at_lincoln_center': False
        },
        'S': {
            'trips': [],
            'trains_stopping_at_grand_army': False,
            'trains_stopping_at_penn_station': False,
            'trains_stopping_at_wall_street': False,
            'trains_stopping_at_lincoln_center': False
        },
    }

    feed_1_2_3 = NYCTFeed("2")
    sorted_trips = sorted(feed_1_2_3.trips, key=lambda trip: trip.stop_time_updates[-1].arrival)
    for trip in sorted_trips:
        # pre-sorting
        # for trip in feed_1_2_3.trips:
        input = {
            "summary": str(trip)
        }
        if trip.route_id not in ['4', '5', '6', '7', 'GS']:
            input['route_id'] = trip.route_id
            stop_time_updates = trip.stop_time_updates
            for update in stop_time_updates:
                if update.arrival is not None:
                    arrival_gmt = update.arrival
                    est = pytz.timezone('US/Eastern')
                    arrival_est = datetime.datetime(arrival_gmt.year, arrival_gmt.month, arrival_gmt.day, arrival_gmt.hour, arrival_gmt.minute, arrival_gmt.second, tzinfo=est)
                    arrival_est = arrival_est - datetime.timedelta(hours=5)
                    arrival_est = arrival_est.strftime('%H:%M')
                else:
                    arrival_est = "-"
                if update.stop_name == 'Grand Army Plaza':
                    input['grand_army_arrival'] = arrival_est
                    output[trip.direction]['trains_stopping_at_grand_army'] = True
                elif update.stop_name == 'Wall St':
                    input['wall_street_arrival'] = arrival_est
                    output[trip.direction]['trains_stopping_at_wall_street'] = True
                elif update.stop_name == '34 St-Penn Station':
                    input['penn_station_arrival'] = arrival_est
                    output[trip.direction]['trains_stopping_at_penn_station'] = True
                elif update.stop_name == '66 St-Lincoln Center':
                    input['lincoln_center_arrival'] = arrival_est
                    output[trip.direction]['trains_stopping_at_lincoln_center'] = True

            output[trip.direction]['trips'].append(input)
    
    response = flask.jsonify(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response
