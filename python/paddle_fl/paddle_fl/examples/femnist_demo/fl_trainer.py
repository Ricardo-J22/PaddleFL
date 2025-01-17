# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from paddle_fl.paddle_fl.core.trainer.fl_trainer import FLTrainerFactory
from paddle_fl.paddle_fl.core.master.fl_job import FLRunTimeJob
import femnist
import numpy
import sys
import paddle
import paddle.fluid as fluid
import logging
import math
import time

logging.basicConfig(
    filename="test.log",
    filemode="w",
    format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
    datefmt="%d-%M-%Y %H:%M:%S",
    level=logging.DEBUG)

trainer_id = int(sys.argv[1])  # trainer id for each guest
job_path = "fl_job_config"
job = FLRunTimeJob()
job.load_trainer_job(job_path, trainer_id)
job._scheduler_ep = "127.0.0.1:9091"  # Inform the scheduler IP to trainer
print(job._target_names)
trainer = FLTrainerFactory().create_fl_trainer(job)
trainer._current_ep = "127.0.0.1:{}".format(9000 + trainer_id)
place = fluid.CPUPlace()
trainer.start(place)
print(trainer._step)
test_program = trainer._main_program.clone(for_test=True)

img = fluid.layers.data(name='img', shape=[1, 28, 28], dtype='float32')
label = fluid.layers.data(name='label', shape=[1], dtype='int64')
feeder = fluid.DataFeeder(feed_list=[img, label], place=fluid.CPUPlace())


def train_test(train_test_program, train_test_feed, train_test_reader):
    acc_set = []
    for test_data in train_test_reader():
        acc_np = trainer.exe.run(program=train_test_program,
                                 feed=train_test_feed.feed(test_data),
                                 fetch_list=["accuracy_0.tmp_0"])
        acc_set.append(float(acc_np[0]))
    acc_val_mean = numpy.array(acc_set).mean()
    return acc_val_mean


epoch_id = 0
step = 0
epoch = 50
count_by_step = False
if count_by_step:
    output_folder = "model_node%d" % trainer_id
else:
    output_folder = "model_node%d_epoch" % trainer_id

while not trainer.stop():
    count = 0
    epoch_id += 1
    if epoch_id > epoch:
        break
    print("{} Epoch {} start train".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), epoch_id))
    # train_data,test_data= data_generater(trainer_id,inner_step=trainer._step,batch_size=64,count_by_step=count_by_step)
    train_reader = paddle.batch(
        paddle.reader.shuffle(
            femnist.train(
                trainer_id,
                inner_step=trainer._step,
                batch_size=64,
                count_by_step=count_by_step),
            buf_size=500),
        batch_size=64)

    test_reader = paddle.batch(
        femnist.test(
            trainer_id,
            inner_step=trainer._step,
            batch_size=64,
            count_by_step=count_by_step),
        batch_size=64)

    if count_by_step:
        for step_id, data in enumerate(train_reader()):
            acc = trainer.run(feeder.feed(data), fetch=["accuracy_0.tmp_0"])
            step += 1
            count += 1
            if count % trainer._step == 0:
                break
    # print("acc:%.3f" % (acc[0]))
    else:
        trainer.run_with_epoch(
            train_reader, feeder, fetch=["accuracy_0.tmp_0"], num_epoch=1)

    acc_val = train_test(
        train_test_program=test_program,
        train_test_reader=test_reader,
        train_test_feed=feeder)

    print("Test with epoch %d, accuracy: %s" % (epoch_id, acc_val))
    save_dir = (output_folder + "/epoch_%d") % epoch_id
    trainer.save_inference_program(save_dir)
