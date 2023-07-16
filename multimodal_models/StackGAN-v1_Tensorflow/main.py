"""
Main File
"""
from tensorflow import keras
import time
import argparse
import os

from data_loader import *
from loss import *
from stage1_model import Stage1_Model
from stage2_model import Stage2_Model

# ## Parse Comamnd Line Arguemnts
parser = argparse.ArgumentParser(description='Main module to initiate training of GAN')
parser.add_argument("--epoch1", default=100, help="Epochs for stage 1. Default is 100", type=int)
parser.add_argument("--epoch2", default=10, help="Epochs for stage 2. Default is 10", type=int)
args = parser.parse_args()

# Create Required Directories if they do not exist
if not os.path.isdir('logs'):
  os.mkdir('logs')
if not os.path.isdir('results_stage1'):
  os.mkdir('results_stage1')
if not os.path.isdir('results_stage2'):
  os.mkdir('results_stage2')



if __name__ == '__main__':

  # Stage 1

  # Define Director/file paths to enable data loading

  data_dir = "./birds"
  train_dir = data_dir + "/train"
  test_dir = data_dir + "/test"
  embeddings_file_path_train = train_dir + "/char-CNN-RNN-embeddings.pickle"
  embeddings_file_path_test = test_dir + "/char-CNN-RNN-embeddings.pickle"
  filenames_file_path_train = train_dir + "/filenames.pickle"
  filenames_file_path_test = test_dir + "/filenames.pickle"
  class_info_file_path_train = train_dir + "/class_info.pickle"
  class_info_file_path_test = test_dir + "/class_info.pickle"
  cub_dataset_dir = "./CUB_200_2011"

  # Some basic parameters/hyper-parameters.
  image_size = 64
  batch_size = 64
  noise_dim = 100
  stage1_generator_lr = 0.0002
  stage1_discriminator_lr = 0.0002
  epochs = args.epoch1
  
  # Define optimizers
  # lr and beta parameters are as defined in paper
  gen_optimizer = keras.optimizers.Adam(learning_rate=stage1_generator_lr, beta_1=0.5, beta_2=0.999)
  dis_optimizer = keras.optimizers.Adam(learning_rate=stage1_discriminator_lr, beta_1=0.5, beta_2=0.999)

  # Dataset Loading

  X_train, y_train, embeddings_train = load_dataset(filenames_file_path=filenames_file_path_train,
                                                    class_info_file_path=class_info_file_path_train,
                                                    cub_dataset_dir=cub_dataset_dir,
                                                    embeddings_file_path=embeddings_file_path_train,
                                                    image_size=(64, 64))
  X_test, y_test, embeddings_test = load_dataset(filenames_file_path=filenames_file_path_test,
                                                 class_info_file_path=class_info_file_path_test,
                                                 cub_dataset_dir=cub_dataset_dir,
                                                 embeddings_file_path=embeddings_file_path_test,
                                                 image_size=(64, 64))


  model_stage1 = Stage1_Model()                                     # Create an object of Stage1_Model class
  stage1_dis = model_stage1.build_stage1_discriminator()
  stage1_dis.compile(loss='binary_crossentropy', optimizer=dis_optimizer)
  stage1_gen = model_stage1.build_stage1_generator()
  stage1_gen.compile(loss="binary_crossentropy", optimizer=gen_optimizer)
  adversarial_model = model_stage1.build_adversarial_model(gen_model=stage1_gen, dis_model=stage1_dis)
  adversarial_model.compile(loss=['binary_crossentropy', KL_loss], loss_weights=[1.0, 1.0],
                            optimizer=gen_optimizer, metrics=None)


  train_writer_stage1 = tf.summary.create_file_writer("logs/stage1/")

  # These labels are passed as ground truth to calculate loss
  real_labels = np.ones((batch_size, 1), dtype=float)
  fake_labels = np.zeros((batch_size, 1), dtype=float)

  print("Beginning Training of Stage 1 .../n")

  for epoch in range(1,epochs+1):
      print("="*20)
      print("Epoch is:", epoch)
      print("Number of batches", int(X_train.shape[0] / batch_size))
      gen_losses = []
      dis_losses = []

      number_of_batches = int(X_train.shape[0] / batch_size)
      for index in range(number_of_batches):  # Here the last batch of size (DATA_SIZE - number_of_batches*batch_size) has been ignored
          
          z_noise = np.random.normal(0, 1, size=(batch_size, noise_dim))
          image_batch = X_train[index * batch_size:(index + 1) * batch_size]
          embedding_batch = embeddings_train[index * batch_size:(index + 1) * batch_size]
          image_batch = (image_batch - 127.5) / 127.5                # Image Scaling


          fake_images, _ = stage1_gen.predict([embedding_batch, z_noise], verbose=3)


          dis_loss_real = stage1_dis.train_on_batch([image_batch, embedding_batch],
                                                    real_labels)
          dis_loss_fake = stage1_dis.train_on_batch([fake_images, embedding_batch],
                                                    fake_labels)
          dis_loss_wrong = stage1_dis.train_on_batch([image_batch[:(batch_size - 1)], embedding_batch[1:]],
                                                     np.reshape(fake_labels[1:], (batch_size-1, 1)))        # Pass in the wrong data by mixing embedding among images
          d_loss = 0.5*(dis_loss_real + 0.5*(dis_loss_wrong + dis_loss_fake))

          g_loss = adversarial_model.train_on_batch([embedding_batch, z_noise, embedding_batch],[real_labels, tf.ones((batch_size, 256))])
          print("g_loss:{}".format(g_loss))
          dis_losses.append(d_loss)
          gen_losses.append(g_loss)

      print("Discriminator Loss over current epoch: {}".format(np.mean(dis_losses)))
      print("Genrator Loss over current epoch: {}".format(np.mean(gen_losses[0])))

      with train_writer_stage1.as_default():
        tf.summary.scalar("discriminator_loss", np.mean(dis_losses), step=epoch)
        tf.summary.scalar("generator_loss", np.mean(gen_losses[0]), step=epoch)

      if epoch % 5 == 0:
          z_noise2 = np.random.normal(0, 1, size=(batch_size, noise_dim))
          embedding_batch = embeddings_test[0:batch_size]
          fake_images, _ = stage1_gen.predict_on_batch([embedding_batch, z_noise2])
          for i, img in enumerate(fake_images[:10]):
              save_rgb_img(img, "results_stage1/gen_{}_{}.png".format(epoch, i))


  stage1_gen.save_weights("stage1_gen.h5")
  stage1_dis.save_weights("stage1_dis.h5")



  # Stage 2

  hr_image_size = (256, 256)   # High Resolution Images
  lr_image_size = (64, 64)     # Low Resoltuion Images
  batch_size = 32
  noise_dim = 100
  stage1_generator_lr = 0.0002
  stage1_discriminator_lr = 0.0002
  epochs = args.epoch2


  # Define optimizers
  dis_optimizer = keras.optimizers.Adam(learning_rate=stage1_discriminator_lr, beta_1=0.5, beta_2=0.999)
  gen_optimizer = keras.optimizers.Adam(learning_rate=stage1_generator_lr, beta_1=0.5, beta_2=0.999)


  # Dataset Loading

  X_hr_train, y_hr_train, embeddings_train = load_dataset(filenames_file_path=filenames_file_path_train,
                                                          class_info_file_path=class_info_file_path_train,
                                                          cub_dataset_dir=cub_dataset_dir,
                                                          embeddings_file_path=embeddings_file_path_train,
                                                          image_size=(256, 256))
  X_hr_test, y_hr_test, embeddings_test = load_dataset(filenames_file_path=filenames_file_path_test,
                                                       class_info_file_path=class_info_file_path_test,
                                                       cub_dataset_dir=cub_dataset_dir,
                                                       embeddings_file_path=embeddings_file_path_test,
                                                       image_size=(256, 256))
  X_lr_train, y_lr_train, _ = load_dataset(filenames_file_path=filenames_file_path_train,
                                           class_info_file_path=class_info_file_path_train,
                                           cub_dataset_dir=cub_dataset_dir,
                                           embeddings_file_path=embeddings_file_path_train,
                                           image_size=(64, 64))
  X_lr_test, y_lr_test, _ = load_dataset(filenames_file_path=filenames_file_path_test,
                                         class_info_file_path=class_info_file_path_test,
                                         cub_dataset_dir=cub_dataset_dir,
                                         embeddings_file_path=embeddings_file_path_test,
                                         image_size=(64, 64))


  model_stage2 = Stage2_Model()
  stage2_dis = model_stage2.build_stage2_discriminator()
  stage2_dis.compile(loss='binary_crossentropy', optimizer=dis_optimizer)
  stage1_gen = model_stage2.build_stage1_generator()
  stage1_gen.compile(loss="binary_crossentropy", optimizer=gen_optimizer)
  stage1_gen.load_weights("stage1_gen.h5")
  stage2_gen = model_stage2.build_stage2_generator()
  stage2_gen.compile(loss="binary_crossentropy", optimizer=gen_optimizer)
  adversarial_model = model_stage2.build_adversarial_model(stage2_gen, stage2_dis, stage1_gen)
  adversarial_model.compile(loss=['binary_crossentropy', KL_loss], loss_weights=[1.0, 1.0],
                            optimizer=gen_optimizer, metrics=None)


  train_writer_stage2 = tf.summary.create_file_writer("logs/stage2/")

  # These labels are passed as ground truth to calculate loss
  real_labels = np.ones((batch_size, 1), dtype=float)
  fake_labels = np.zeros((batch_size, 1), dtype=float)

  print("Beginning Training of Stage 2 .../n")

  for epoch in range(1,epochs+1):
      print("="*20)
      print("Epoch is:", epoch)
      gen_losses = []
      dis_losses = []

      number_of_batches = int(X_hr_train.shape[0] / batch_size)
      print("Number of batches:{}".format(number_of_batches))
      for index in range(number_of_batches):          # Here the last batch of size (DATA_SIZE - number_of_batches*batch_size) has been ignored

          z_noise = np.random.normal(0, 1, size=(batch_size, noise_dim))
          X_hr_train_batch = X_hr_train[index * batch_size:(index + 1) * batch_size]
          embedding_batch = embeddings_train[index * batch_size:(index + 1) * batch_size]
          X_hr_train_batch = (X_hr_train_batch - 127.5) / 127.5

          lr_fake_images, _ = stage1_gen.predict([embedding_batch, z_noise], verbose=3)               # Low Resolution Fake Images
          hr_fake_images, _ = stage2_gen.predict([embedding_batch, lr_fake_images], verbose=3)        # High Resolution Fake Images


          dis_loss_real = stage2_dis.train_on_batch([X_hr_train_batch, embedding_batch],
                                                    real_labels)
          dis_loss_fake = stage2_dis.train_on_batch([hr_fake_images, embedding_batch],
                                                    fake_labels)
          dis_loss_wrong = stage2_dis.train_on_batch([X_hr_train_batch[:(batch_size - 1)], embedding_batch[1:]],
                                                     np.reshape(fake_labels[1:], (batch_size-1, 1)))
          d_loss = 0.5*(dis_loss_real + 0.5*(dis_loss_wrong + dis_loss_fake))

          g_loss = adversarial_model.train_on_batch([embedding_batch, z_noise, embedding_batch],
                                                              [tf.ones((batch_size, 1)), tf.ones((batch_size, 256))])


      print("Discriminator Loss over current epoch: {}".format(np.mean(dis_losses)))
      print("Genrator Loss over current epoch: {}".format(np.mean(gen_losses[0])))

      with train_writer_stage2.as_default():
        tf.summary.scalar("discriminator_loss", np.mean(dis_losses), step=epoch)
        tf.summary.scalar("generator_loss", np.mean(gen_losses[0]), step=epoch)


      if epoch % 2 == 0:
          z_noise2 = np.random.normal(0, 1, size=(batch_size, noise_dim))
          embedding_batch = embeddings_test[0:batch_size]
          lr_fake_images, _ = stage1_gen.predict([embedding_batch, z_noise2], verbose=3)
          hr_fake_images, _ = stage2_gen.predict([embedding_batch, lr_fake_images], verbose=3)
          for i, img in enumerate(hr_fake_images[:10]):
              save_rgb_img(img, "results_stage2/gen_{}_{}.png".format(epoch, i))


  stage2_gen.save_weights("stage2_gen.h5")
  stage2_dis.save_weights("stage2_dis.h5")