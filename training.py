import os
import numpy as np
import pickle
import random
import json
import nltk
from nltk.stem import WordNetLemmatizer
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
from tensorflow.keras.optimizers import SGD

# nltk.download('punkt')
# nltk.download('wordnet')

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

lemmatizer = WordNetLemmatizer()
intents = json.load(open('intents.json'))

words, classes, documents = [], [], []
ignore_symbols = ['?', '!', '.', ',']


for intent in intents['intents']:
    for pattern in intent['patterns']:
        word_list = nltk.word_tokenize(pattern)
        words.extend(word_list)
        documents.append((word_list, intent['tag']))
        if intent['tag'] not in classes:
            classes.append(intent['tag'])

words = [lemmatizer.lemmatize(w.lower()) for w in words if w not in ignore_symbols]
words = sorted(set(words))
classes = sorted(set(classes))

os.makedirs('model', exist_ok=True)
pickle.dump(words, open('model/words.pkl', 'wb'))
pickle.dump(classes, open('model/classes.pkl', 'wb'))


training = []
output_empty = [0] * len(classes)

for doc in documents:
    bag = []
    word_patterns = [lemmatizer.lemmatize(w.lower()) for w in doc[0] if w not in ignore_symbols]

    for w in words:
        bag.append(1 if w in word_patterns else 0)

    output_row = list(output_empty)
    output_row[classes.index(doc[1])] = 1
    training.append([bag, output_row])

random.shuffle(training)

train_x = np.array([t[0] for t in training])
train_y = np.array([t[1] for t in training])


model = Sequential()
model.add(Dense(128, input_shape=(train_x.shape[1],), activation='relu'))
model.add(Dropout(0.5))
model.add(Dense(64, activation='relu'))
model.add(Dropout(0.5))
model.add(Dense(train_y.shape[1], activation='softmax'))

sgd = SGD(learning_rate=0.01, momentum=0.9, nesterov=True)
model.compile(loss='categorical_crossentropy', optimizer=sgd, metrics=['accuracy'])

model.fit(train_x, train_y, epochs=200, batch_size=5, verbose=1)
model.save('model/chatbot_model.keras')