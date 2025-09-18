from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='templates')

# Lazy import of heavy backend modules occurs inside routes to keep startup fast
def _get_main():
    import importlib
    return importlib.import_module('main')

import updates


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/handle_message', methods=['POST'])
def handle_message():
    message = request.json.get('message', '')

    # Attempt to import the ML backend lazily. If importing or running the
    # model fails (for example, NLTK not installed in this interpreter),
    # return a helpful fallback with latest updates so the frontend can still
    # provide value to the user.
    try:
        main = _get_main()
    except Exception as e:
        tips = updates.fetch_latest_disaster_updates('general')
        fall_text = "I couldn't access the model right now, but here are some important tips and latest updates:\n\n"
        fall_text += "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        return jsonify({'response': fall_text}), 503

    try:
        intents_list = main.predict_class(message)
        response = main.get_response(intents_list, main.intents)
        return jsonify({'response': response})
    except Exception as e:
        # If runtime error occurs while predicting, return updates instead of 500 stack
        tips = updates.fetch_latest_disaster_updates('general')
        fall_text = "An error occurred while generating a response. Here are some important tips and latest updates:\n\n"
        fall_text += "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        return jsonify({'response': fall_text}), 500


@app.route('/latest_updates', methods=['POST'])
def latest_updates():
    data = request.json or {}
    tag = data.get('tag', 'general')
    tips = updates.fetch_latest_disaster_updates(tag)
    return jsonify({'updates': tips})


# curl -X POST http://127.0.0.1:5000/handle_message -d '{"message":"what is coding"}' -H "Content-Type: application/json"


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)