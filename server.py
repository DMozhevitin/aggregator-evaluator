"""
We have the following database schema:
    conn = sqlite3.connect('aggregator.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS swaps
                 (utime INTEGER, aggregator TEXT, swap_type TEXT, real_output REAL, loss_ratio REAL, short_descriptions_out TEXT, short_descriptions_in TEXT, gas_fees REAL)''')
"""

"""
We want to show on webpage a few similar graphs.
Each graph corresponds to a given swap_type and shows data for prev 24 hours.

Graph shows placement of the aggregator among other measured by loss ratio:
the higher the loss ratio, the higher the aggregator is placed. That means if 
aggregator1 has loss 1.0, aggregator2 has loss 0.5, and aggregator3 has loss 0.7,
then aggregator1 has place 1, aggregator2 has place 3, and aggregator3 has place 2.

Name of the aggregator should be shown on the legend.

It also should be shown higher that means y axis is reversed with 1 at the top and 6 at the bottom.

When we place cursor upon graph point, we should see the following information:
- real_output
- loss_ratio
- short_descriptions_out
- gas_fees
"""

"""
We want to use simples webserver possible: SimpleHTTPServer.
"""

import sqlite3
import json
import http.server
from datetime import datetime
from datetime import timedelta

template = """
<!DOCTYPE html>

<html>
<head>
    <title>Graphs</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div id="graph_1ton_usdt"></div>
    <script>
        var data = %(1ton_usdt)s;
        var layout = {
            title: 'Swap 1 ton->USDT',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_1ton_usdt', data, layout);
    </script>
    <div id="graph_100ton_usdt"></div>
    <script>
        var data = %(100ton_usdt)s;
        var layout = {
            title: 'Swap 100 ton->USDT',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_100ton_usdt', data, layout);
    </script>

        <div id="graph_10000ton_usdt"></div>
    <script>
        var data = %(10000ton_usdt)s;
        var layout = {
            title: 'Swap 10000 ton->USDT',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_10000ton_usdt', data, layout);
    </script>

    <div id="graph_1ton_raff"></div>
    <script>
        var data = %(1ton_raff)s;
        var layout = {
            title: 'Swap 1 ton->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_1ton_raff', data, layout);
    </script>
    <div id="graph_100ton_raff"></div>
    <script>
        var data = %(100ton_raff)s;
        var layout = {
            title: 'Swap 100 ton->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_100ton_raff', data, layout);
    </script>

        <div id="graph_10000ton_raff"></div>
    <script>
        var data = %(10000ton_raff)s;
        var layout = {
            title: 'Swap 10000 ton->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_10000ton_raff', data, layout);
    </script>

    

    <div id="graph_1usdt_raff"></div>
    <script>
        var data = %(1usdt_raff)s;
        var layout = {
            title: 'Swap 1 usdt->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_1usdt_raff', data, layout);
    </script>
    <div id="graph_100usdt_raff"></div>
    <script>
        var data = %(100usdt_raff)s;
        var layout = {
            title: 'Swap 100 usdt->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_100usdt_raff', data, layout);
    </script>

        <div id="graph_10000usdt_raff"></div>
    <script>
        var data = %(10000usdt_raff)s;
        var layout = {
            title: 'Swap 10000 usdt->RAFF',
            yaxis: {
                autorange: 'reversed'
            },
            "xaxis": {
                "type": 'date'
            }
        };
        Plotly.newPlot('graph_10000usdt_raff', data, layout);
    </script>
</body>
</html>
"""

def get_data(swap_type):
    conn = sqlite3.connect('aggregator.db')
    c = conn.cursor()
    c.execute("SELECT * FROM swaps WHERE swap_type = ? AND utime > ?", (swap_type, int((datetime.now() - timedelta(days=1)).timestamp())))
    data = c.fetchall()
    conn.close()
    return data

def convert_route(routes):
    """
    We have routes as list of route, where each route is dict:
                    { "DEX": "name",
                      "IN": <amount>,
                      "IN_ASSET_SHORT": <symbol>,
                      "OUT_ASSET_SHORT": <symbol>)
                     }
    or
                        {
                        "DEX": "UNKNOWN",
                        "IN": <amount>,
                        "IN_ASSET_SHORT": <symbol>
                    }
    We want to find sum of IN in all routes
    and then output list of strings in format:
    DEX: IN_ASSET_SHORT -> OUT_ASSET_SHORT PERCENTAGE%
    """
    total = sum([int(x["IN"]) for x in routes])
    return "</br>".join([f"{x['DEX']}: {x.get('IN_ASSET_SHORT', '?')} -> {x.get('OUT_ASSET_SHORT', '?')} {float(x['IN'])/total*100:.2f}%" for x in routes]) 
    


def get_graph(swap_type):
    data = get_data(swap_type)
    # we want to group data points by time
    # the inside group find placement for each aggregator
    # then plot line for each aggregator

    timepoints = {}
    for x in data:
        timepoints[x[0]] = timepoints.get(x[0], [])
        timepoints[x[0]].append(list(x))
    
    # augment data with placement
    for timepoint in timepoints:
        timepoints[timepoint] = sorted(timepoints[timepoint], key=lambda x: -x[4])
        for i, x in enumerate(timepoints[timepoint]):
            if i != 0 and x[4] == timepoints[timepoint][i-1][4]:
                x.append(i)
            else:
                x.append(i+1)
    
    data = []

    aggreagators = {}
    # now we want separate lines for each aggregator, with y equal to placement
    default_colors = {"Coffee.swap": "#37262c", "DeDust": "#ffb304"}
    for timepoint in timepoints:        
        for x in timepoints[timepoint]:
            name = x[1]
            if not name in aggreagators:
                aggreagators[name] = {
                    "x": [],
                    "y": [],
                    "mode": "lines+markers",
                    "name": name,
                    "text": []
                }
                if name in default_colors:
                    aggreagators[name]["line"] = {"color": default_colors[name]}
            
            aggreagators[name]["x"].append(timepoint*1000)
            aggreagators[name]["y"].append(x[8])
            aggreagators[name]["text"].append(f"real_output: {x[3]}</br>loss_ratio: {x[4]}</br>gas_fees: {x[7]}</br>{convert_route(json.loads(x[5]))}")
    
    for name in aggreagators:
        data.append(aggreagators[name])

    return json.dumps(data)
    #return template % ()

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            USDT = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
            ton = "ton"
            RAFF = "EQCJbp0kBpPwPoBG-U5C-cWfP_jnksvotGfArPF50Q9Qiv9h"

            data = {"1ton_usdt": get_graph(f"1 {ton}->{USDT}"),
                    "100ton_usdt": get_graph(f"100 {ton}->{USDT}"),
                    "10000ton_usdt": get_graph(f"10000 {ton}->{USDT}"),
                    "1ton_raff": get_graph(f"1 {ton}->{RAFF}"),
                    "100ton_raff": get_graph(f"100 {ton}->{RAFF}"),
                    "10000ton_raff": get_graph(f"10000 {ton}->{RAFF}"),
                    "1usdt_raff": get_graph(f"1 {USDT}->{RAFF}"),
                    "100usdt_raff": get_graph(f"100 {USDT}->{RAFF}"),
                    "10000usdt_raff": get_graph(f"10000 {USDT}->{RAFF}"),
            }
            self.wfile.write((template % data).encode())
            #self.wfile.write(get_graph("1 ton->EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs").encode())
        else:
            super().do_GET()

httpd = http.server.HTTPServer(('0.0.0.0', 8000), MyHandler)
httpd.serve_forever()
