#!/usr/bin/env python

from __future__ import print_function

print('### IMPORTING MODULES ###')

import cv2
import datetime
import numpy as np
import os
import sys
import time

from keras.models import Model, model_from_json
from keras.layers import Dense, Dropout, Activation, Flatten, Input, Reshape, merge
from keras.layers import Convolution2D, MaxPooling2D
from keras.optimizers import SGD
from keras.utils import np_utils
from keras.callbacks import History, ModelCheckpoint
from keras import backend as K


np.random.seed(None) 
dateTimeStr = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H%M%S')


#TODO argparse with defaults
BATCH_SIZE = 32
NB_EPOCH = 1000 #1000
IMG_ROWS, IMG_COLS = 640, 480
DATA_DIR = '/media/jrussino/DATA1/data/vd_depth/'
LEARNING_RATE = 0.1 # used 0.1 for coarse
MOMENTUM = 0.9
OUTDIR = '/media/jrussino/DATA1/models/'
#OUTDIR = '/home/jrussino/tb_drive/models/'
MODE = 'eval' # ["train_coarse", "train_fine", "eval"]]
## TRAINED COARSE
MODEL_FILE = '/media/jrussino/DATA1/models/2016-09-06-230359/model_2016-09-06-130439.json'
WEIGHTS_FILE = '/media/jrussino/DATA1/models/2016-09-06-230359/weights-final_2016-09-06-130439.h5'
## TRAINED FINE
#MODEL_FILE = 
#WEIGHTS_FILE = 
LAMBDA = 0.5


def reshapeAndScale(data):
    if len(data.shape) == 3:
        data = data.reshape(data.shape[0], data.shape[2], data.shape[1])
    else:
        data = data.reshape(data.shape[0], data.shape[3], data.shape[2], data.shape[1])
    data = data.astype('float32')
    data /= 255
    return data

def loadData(dataDir):
    X_files = [os.path.join(dataDir, f) for f in os.listdir(dataDir) if '_image' in f] 
    X = np.array([cv2.pyrDown(cv2.imread(f)) for f in X_files])
    X = reshapeAndScale(X)

    Y_files = [f.replace('_image', '_depth') for f in X_files]
    Y = np.array([cv2.pyrDown(cv2.pyrDown(cv2.pyrDown(cv2.imread(f, 0)))) for f in Y_files])
    Y = reshapeAndScale(Y)
    return X, Y

def scale_invariant_error(y_true, y_pred):
    first_log = K.log(K.clip(y_pred, K.epsilon(), np.inf) + 1.)
    second_log = K.log(K.clip(y_true, K.epsilon(), np.inf) + 1.)
    return K.mean(K.square(first_log - second_log), axis=-1) - LAMBDA * K.square(K.mean(first_log - second_log, axis=-1))

def toImage(data) :
    data *= 255
    data = data.astype('uint8')
    if len(data.shape) == 2:
        data = data.reshape((data.shape[1], data.shape[0]))
    elif data.shape[0] == 1:
        data = data.reshape((data.shape[2], data.shape[1]))
    else:
        data = data.reshape((data.shape[2], data.shape[1], data.shape[0]))
    return data


print(MODE)
if MODE == 'train_coarse':
    # Input:
    inputs = Input(shape=(3, IMG_ROWS/2, IMG_COLS/2))

    # Coarse 1:
    # 11x11 conv, 4 stride, ReLU activation, 2x2 pool
    coarse_1 = Convolution2D(96, 11, 11, border_mode='same', init='uniform', subsample=(4,4), input_shape=(1,IMG_ROWS/2, IMG_COLS/2), name='coarse_1')(inputs)
    coarse_1 = Activation('relu')(coarse_1)
    coarse_1 = MaxPooling2D(pool_size=(2, 2))(coarse_1)

    # Coarse 2:
    # 5x5 conv, 1 stride, ReLU activation, 2x2 pool
    coarse_2 = Convolution2D(256, 5, 5, border_mode='same', init='uniform', name='coarse_2')(coarse_1)
    coarse_2 = Activation('relu')(coarse_2)
    coarse_2 = MaxPooling2D(pool_size=(2, 2))(coarse_2)

    # Coarse 3:
    # 3x3 conv, 1 stride, ReLU activation, no pool
    coarse_3 = Convolution2D(384, 3, 3, border_mode='same', init='uniform', name='coarse_3')(coarse_2)
    coarse_3 = Activation('relu')(coarse_3)

    # Coarse 4:
    # 3x3 conv, 1 stride, ReLU activation, no pool
    coarse_4 = Convolution2D(384, 3, 3, border_mode='same', init='uniform', name='coarse_4')(coarse_3)
    coarse_4 = Activation('relu')(coarse_4)

    # Coarse 5:
    # 3x3 conv, 1 stride, ReLU activation, 2x2 pool?
    coarse_5 = Convolution2D(256, 3, 3, border_mode='same', init='uniform', name='coarse_5')(coarse_4)
    coarse_5 = Activation('relu')(coarse_5)
    coarse_5 = MaxPooling2D(pool_size=(2, 2))(coarse_5)

    # Coarse 6:
    # Fully-connected, ReLU activation, followed by dropout
    coarse_6 = Flatten(name='coarse_6')(coarse_5)
    coarse_6 = Dense(4096, init='uniform')(coarse_6)
    coarse_6 = Activation('relu')(coarse_6)
    coarse_6 = Dropout(0.5)(coarse_6)

    # Coarse 7:
    # Fully-connected, linear activation
    coarse_7 = Dense((IMG_ROWS/8)*(IMG_COLS/8), init='uniform', name='coarse_7')(coarse_6)
    coarse_7 = Activation('linear')(coarse_7)
    coarse_7 = Reshape((IMG_ROWS/8, IMG_COLS/8))(coarse_7)

    # compile the model
    print('### COMPILING MODEL ###')
    model = Model(input=inputs, output=coarse_7)
    model.compile(loss=scale_invariant_error, optimizer=SGD(lr=LEARNING_RATE, momentum=MOMENTUM), metrics=['accuracy'])
    model.summary()

    # save the model architecture to file
    print('### SAVING MODEL ARCHITECTURE ###')
    modelDir = dateTimeStr;
    os.mkdir(os.path.join(OUTDIR, modelDir))
    modelFile = os.path.join(OUTDIR, modelDir, 'depth_coarse_model_{}.json'.format(dateTimeStr))
    print(model.to_json(), file=open(modelFile, 'w'))

    # load and preprocess the data
    print('### LOADING DATA ###')
    X_train, Y_train = loadData(os.path.join(DATA_DIR, 'train/'))
    X_test , Y_test = loadData(os.path.join(DATA_DIR, 'test/'))
    print('X_train shape:', X_train.shape)
    print('Y_train shape:', Y_train.shape)
    print(X_train.shape[0], 'train samples')
    print(X_test.shape[0], 'test samples')

    # train the model
    print('### TRAINING ###')
    history_cb = History()
    checkpointFile = os.path.join(OUTDIR, modelDir, 'coarse-weights-improvement-{epoch:02d}-{val_acc:.2f}.hdf5') 
    checkpoint_cb = ModelCheckpoint(filepath=checkpointFile, monitor='val_loss', verbose=1, save_best_only=True, save_weights_only=True, mode='auto')
    model.fit(X_train, Y_train, nb_epoch=NB_EPOCH, batch_size=BATCH_SIZE,
            verbose=1, validation_data=(X_test, Y_test), callbacks=[history_cb, checkpoint_cb])
    histFile = os.path.join(OUTDIR, modelDir, 'depth_coarse_hist_{}.h5'.format(dateTimeStr))

    # save the model weights to file
    print('### SAVING TRAINED MODEL ###')
    print(history_cb.history, file=open(histFile, 'w'))
    weightsFile = os.path.join(OUTDIR, modelDir, 'depth_coarse_weights_{}.h5'.format(dateTimeStr))
    model.save_weights(weightsFile)

    # evaluate the trained model
    print('sleeping for 5 seconds...')
    time.sleep(5)
    print('### LOADING THE MODEL WEIGHTS ###')
    model_json = open(modelFile, 'r').read()
    model2 = model_from_json(model_json)
    model2.load_weights(weightsFile)
    model2.compile(loss=scale_invariant_error, optimizer=SGD(lr=LEARNING_RATE, momentum=MOMENTUM), metrics=['accuracy'])

    # evaluate the model
    print('### EVALUATING ###')
    score = model2.evaluate(X_test, Y_test, verbose=1)
    print('Test score:', score[0])
    print('Test accuracy:', score[1])


if MODE == 'train_fine':

    # load coarse model
    print('### LOADING SAVED MODEL AND WEIGHTS ###')
    model_json = open(MODEL_FILE, 'r').read()
    model = model_from_json(model_json)
    model.load_weights(WEIGHTS_FILE)
    
    # freeze training on coarse layers
    for layer in model.layers:
        layer.trainable = False

    # modify with additional fine layers
    print('### UPDATING MODEL ###')
    # Input:
    inputs = model.inputs[0]

    # Fine 1:
    # 9x9 conv, 2 stride, ReLU activation, 2x2 pool
    fine_1 = Convolution2D(63, 9, 9, border_mode='same', init='uniform', subsample=(2,2), input_shape=(1, IMG_ROWS/2, IMG_COLS/2), name='fine_1_conv')(inputs)
    fine_1 = Activation('relu', name='fine_1_relu')(fine_1)
    fine_1 = MaxPooling2D(pool_size=(2, 2), name='fine_1_pool')(fine_1)

    # Fine 2:
    # Concatenation with Coarse 7
    coarse_out = model.outputs[0]
    coarse_out = Reshape((1, IMG_ROWS/8, IMG_COLS/8), name='coarse_out_reshape')(coarse_out)
    fine_2 = merge([fine_1, coarse_out], mode='concat', concat_axis=1, name='fine_2_merge')

    # Fine 3:
    # 5x5 conv, 1 stride, ReLU activation, no pool
    fine_3 = Convolution2D(64, 5, 5, border_mode='same', init='uniform', subsample=(1,1), name='fine_3_conv')(fine_2)
    fine_3 = Activation('relu', name='fine_3_relu')(fine_3)

    # Fine 4:
    # 5x5 conv, 1 stride, linear activation, no pool
    fine_4 = Convolution2D(1, 5, 5, border_mode='same', init='uniform', subsample=(1,1), name='fine_4_conv')(fine_3)
    fine_4 = Activation('linear', name='fine_4_linear')(fine_4)
    fine_4 = Reshape((IMG_ROWS/8, IMG_COLS/8), name='fine_4_reshape')(fine_4)

    # compile the model
    print('### COMPILING MODEL ###')
    model = Model(input=inputs, output=fine_4)
    model.compile(loss=scale_invariant_error, optimizer=SGD(lr=LEARNING_RATE, momentum=MOMENTUM), metrics=['accuracy'])
    model.summary()

    # save the model architecture to file
    print('### SAVING MODEL ARCHITECTURE ###')
    modelDir = dateTimeStr;
    os.mkdir(os.path.join(OUTDIR, modelDir))
    modelFile = os.path.join(OUTDIR, modelDir, 'depth_fine_model_{}.json'.format(dateTimeStr))
    print(model.to_json(), file=open(modelFile, 'w'))

    # load and preprocess the data
    print('### LOADING DATA ###')
    X_train, Y_train = loadData(os.path.join(DATA_DIR, 'train/'))
    X_test , Y_test = loadData(os.path.join(DATA_DIR, 'test/'))
    print('X_train shape:', X_train.shape)
    print('Y_train shape:', Y_train.shape)
    print(X_train.shape[0], 'train samples')
    print(X_test.shape[0], 'test samples')

    # train the model
    print('### TRAINING ###')
    history_cb = History()
    checkpointFile = os.path.join(OUTDIR, modelDir, 'fine-weights-improvement-{epoch:02d}-{val_acc:.2f}.hdf5') 
    checkpoint_cb = ModelCheckpoint(filepath=checkpointFile, monitor='val_loss', verbose=1, save_best_only=True, save_weights_only=True, mode='auto')
    model.fit(X_train, Y_train, nb_epoch=NB_EPOCH, batch_size=BATCH_SIZE,
            verbose=1, validation_data=(X_test, Y_test), callbacks=[history_cb, checkpoint_cb])
    histFile = os.path.join(OUTDIR, modelDir, 'depth_fine_hist_{}.json'.format(dateTimeStr))

    # save the model weights to file
    print('### SAVING TRAINED MODEL ###')
    print(history_cb.history, file=open(histFile, 'w'))
    weightsFile = os.path.join(OUTDIR, modelDir, 'depth_fine_weights_{}.h5'.format(dateTimeStr))
    model.save_weights(weightsFile)

    # evaluate the trained model
    print('sleeping for 5 seconds...')
    time.sleep(5)
    print('### LOADING THE MODEL WEIGHTS ###')
    model_json = open(modelFile, 'r').read()
    model2 = model_from_json(model_json)
    model2.load_weights(weightsFile)
    model2.compile(loss=scale_invariant_error, optimizer=SGD(lr=LEARNING_RATE, momentum=MOMENTUM), metrics=['accuracy'])

    # evaluate the model
    print('### EVALUATING ###')
    score = model2.evaluate(X_test, Y_test, verbose=1)
    print('Test score:', score[0])
    print('Test accuracy:', score[1])


if MODE == 'eval':
    # load coarse model
    print('### LOADING SAVED MODEL AND WEIGHTS ###')
    model_json = open(MODEL_FILE, 'r').read()
    model = model_from_json(model_json)
    model.load_weights(WEIGHTS_FILE)
    model.compile(loss=scale_invariant_error, optimizer=SGD(lr=LEARNING_RATE, momentum=MOMENTUM), metrics=['accuracy'])
    model.summary()

    # load and preprocess the data
    print('### LOADING DATA ###')
    X_train, Y_train = loadData(os.path.join(DATA_DIR, 'train/'))
    X_test , Y_test = loadData(os.path.join(DATA_DIR, 'test/'))
    print('X_train shape:', X_train.shape)
    print('Y_train shape:', Y_train.shape)
    print(X_train.shape[0], 'train samples')
    print(X_test.shape[0], 'test samples')

    # evaluate the model
    print('### EVALUATING ###')
    score = model.evaluate(X_test, Y_test, verbose=1)
    print('Test score:', score[0])
    print('Test accuracy:', score[1])
        
    # show test samples
    for _ in range(100):
        random_index = np.random.randint(X_test.shape[0])
        print('random index: {}'.format(random_index))
        x = X_test[random_index]
        y = Y_test[random_index]
        print('x: {}'.format(x.shape))
        print('y: {}'.format(y.shape))

        p = model.predict(np.array([x]), batch_size=1)
        print('p: {}'.format(p.shape))

        x_img = toImage(x)
        y_img = toImage(y)
        p_img = toImage(p)

        cv2.imshow('input', x_img)
        cv2.imshow('prediction', p_img)
        cv2.imshow('ground truth', y_img)
        cv2.waitKey(0)
