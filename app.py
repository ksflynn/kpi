from flask import Flask
from nyct_gtfs import NYCTFeed

app = Flask(__name__)

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
    for trip in feed_1_2_3.trips:
        input = {
            "summary": str(trip)
        }
        if trip.route_id not in ['4', '5', '6', '7', 'GS']:
            stop_time_updates = trip.stop_time_updates
            for update in stop_time_updates:
                if update.stop_name == 'Grand Army Plaza':
                    input['grand_army_arrival'] = update.arrival
                    output[trip.direction]['trains_stopping_at_grand_army'] = True
                elif update.stop_name == 'Wall St':
                    input['wall_street_arrival'] = update.arrival
                    output[trip.direction]['trains_stopping_at_wall_street'] = True
                elif update.stop_name == '34 St-Penn Station':
                    input['penn_station_arrival'] = update.arrival
                    output[trip.direction]['trains_stopping_at_penn_station'] = True
                elif update.stop_name == '66 St-Lincoln Center':
                    input['lincoln_center_arrival'] = update.arrival
                    output[trip.direction]['trains_stopping_at_lincoln_center'] = True

            output[trip.direction]['trips'].append(input)
    return output
