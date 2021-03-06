# -*- coding:utf-8 -*-
__author__ = 'Randolph'

import os
import sys
import time
import logging
import numpy as np

sys.path.append('../')
logging.getLogger('tensorflow').disabled = True

import tensorflow as tf

from utils import checkmate as cm
from utils import data_helpers as dh
from utils import param_parser as parser
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

args = parser.parameter_parser()
MODEL = dh.get_model_name()
logger = dh.logger_fn("tflog", "logs/Test-{0}.log".format(time.asctime()))

CPT_DIR = 'runs/' + MODEL + '/checkpoints/'
BEST_CPT_DIR = 'runs/' + MODEL + '/bestcheckpoints/'
SAVE_DIR = 'output/' + MODEL


def test_sann():
    """Test SANN model."""
    # Print parameters used for the model
    dh.tab_printer(args, logger)

    # Load data
    logger.info("Loading data...")
    logger.info("Data processing...")
    test_data = dh.load_data_and_labels(args.test_file, args.word2vec_file)

    logger.info("Data padding...")
    x_test_front, x_test_behind, y_test = dh.pad_data(test_data, args.pad_seq_len)

    # Load sann model
    OPTION = dh._option(pattern=1)
    if OPTION == 'B':
        logger.info("Loading best model...")
        checkpoint_file = cm.get_best_checkpoint(BEST_CPT_DIR, select_maximum_value=True)
    else:
        logger.info("Loading latest model...")
        checkpoint_file = tf.train.latest_checkpoint(CPT_DIR)
    logger.info(checkpoint_file)

    graph = tf.Graph()
    with graph.as_default():
        session_conf = tf.ConfigProto(
            allow_soft_placement=args.allow_soft_placement,
            log_device_placement=args.log_device_placement)
        session_conf.gpu_options.allow_growth = args.gpu_options_allow_growth
        sess = tf.Session(config=session_conf)
        with sess.as_default():
            # Load the saved meta graph and restore variables
            saver = tf.train.import_meta_graph("{0}.meta".format(checkpoint_file))
            saver.restore(sess, checkpoint_file)

            # Get the placeholders from the graph by name
            input_x_front = graph.get_operation_by_name("input_x_front").outputs[0]
            input_x_behind = graph.get_operation_by_name("input_x_behind").outputs[0]
            input_y = graph.get_operation_by_name("input_y").outputs[0]
            dropout_keep_prob = graph.get_operation_by_name("dropout_keep_prob").outputs[0]
            is_training = graph.get_operation_by_name("is_training").outputs[0]

            # Tensors we want to evaluate
            predictions = graph.get_operation_by_name("output/predictions").outputs[0]
            topKPreds = graph.get_operation_by_name("output/topKPreds").outputs[0]
            loss = graph.get_operation_by_name("loss/loss").outputs[0]

            # Split the output nodes name by '|' if you have several output nodes
            output_node_names = "output/predictions|output/topKPreds"

            # Save the .pb model file
            output_graph_def = tf.graph_util.convert_variables_to_constants(sess, sess.graph_def,
                                                                            output_node_names.split("|"))
            tf.train.write_graph(output_graph_def, "graph", "graph-sann-{0}.pb".format(MODEL), as_text=False)

            # Generate batches for one epoch
            batches_test = dh.batch_iter(list(zip(x_test_front, x_test_behind, y_test)),
                                         args.batch_size, 1, shuffle=False)

            # Collect the predictions here
            test_counter, test_loss = 0, 0.0
            all_labels = []
            all_predicted_labels = []
            all_predicted_scores = []

            for batch_test in batches_test:
                x_batch_test_front, x_batch_test_behind, y_batch_test = zip(*batch_test)
                feed_dict = {
                    input_x_front: x_batch_test_front,
                    input_x_behind: x_batch_test_behind,
                    input_y: y_batch_test,
                    dropout_keep_prob: 1.0,
                    is_training: False
                }

                batch_predicted_labels, batch_predicted_scores, batch_loss \
                    = sess.run([predictions, topKPreds, loss], feed_dict)

                for i in y_batch_test:
                    all_labels.append(np.argmax(i))
                for j in batch_predicted_scores:
                    all_predicted_scores.append(j[0])
                for k in batch_predicted_labels:
                    all_predicted_labels.append(k)

                test_loss = test_loss + batch_loss
                test_counter = test_counter + 1

            test_loss = float(test_loss / test_counter)

            # Calculate Precision & Recall & F1
            test_acc = accuracy_score(y_true=np.array(all_labels), y_pred=np.array(all_predicted_labels))
            test_pre = precision_score(y_true=np.array(all_labels),
                                       y_pred=np.array(all_predicted_labels), average='micro')
            test_rec = recall_score(y_true=np.array(all_labels),
                                    y_pred=np.array(all_predicted_labels), average='micro')
            test_F1 = f1_score(y_true=np.array(all_labels),
                               y_pred=np.array(all_predicted_labels), average='micro')

            # Calculate the average AUC
            test_auc = roc_auc_score(y_true=np.array(all_labels),
                                     y_score=np.array(all_predicted_scores), average='micro')

            logger.info("All Test Dataset: Loss {0:g} | Acc {1:g} | Precision {2:g} | "
                        "Recall {3:g} | F1 {4:g} | AUC {5:g}"
                        .format(test_loss, test_acc, test_pre, test_rec, test_F1, test_auc))

            # Save the prediction result
            if not os.path.exists(SAVE_DIR):
                os.makedirs(SAVE_DIR)
            dh.create_prediction_file(output_file=SAVE_DIR + "/predictions.json", front_data_id=test_data.front_testid,
                                      behind_data_id=test_data.behind_testid, all_labels=all_labels,
                                      all_predict_labels=all_predicted_labels, all_predict_scores=all_predicted_scores)

    logger.info("All Done.")


if __name__ == '__main__':
    test_sann()
