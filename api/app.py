from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/alerts")
def get_alerts():
    return jsonify([])

@app.route("/heatmap/<camera>")
def get_heatmap(camera):
    return "heatmap"
