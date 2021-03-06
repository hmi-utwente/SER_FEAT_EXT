from __future__ import print_function
import numpy as np
import argparse
import csv
import h5py
import random

np.random.seed(1337)  # for reproducibility

parser = argparse.ArgumentParser()
parser.add_argument("-input", "--input", dest= 'input', type=str, help="meta file including a list of feature files and labels")
parser.add_argument("-mt", "--multitasks", dest= 'multitasks', type=str, help="index of tasks in a meta file (idx:idx:..)", default = '3:4:5:6:7')
parser.add_argument("-f_idx", "--feat_idx", dest= 'feat_idx', type=int, help="index of feature file in a meta file(e.g. 8)", default = '8')
parser.add_argument("-c_idx", "--c_idx", dest= 'c_idx', type=int, help="cross-validation index (e.g. 3)", default = '3')
parser.add_argument("-n_cc", "--n_cc", dest= 'n_cc', type=int, help="number of cross validations", default = '0')

parser.add_argument("-m_steps", "--max_time_steps", dest= 'max_time_steps', type=int, help="maximum time steps(#samples) per utterance", default = '50')
parser.add_argument("-c_len", "--context_length", dest= 'context_length', type=int, help="context window length (#samples)", default = '1')

parser.add_argument("-out", "--output", dest= 'output', type=str, help="output file in HDF5", default="./output")
parser.add_argument("-base", "--base_dir", dest= 'base_dir', type=str, help="base_dir for feature files")
parser.add_argument("-f_delim", "--feat_delim", dest= 'feat_delim', type=str, help="deliminator for features", default=";")


parser.add_argument("--two_d", help="two_d",
                    action="store_true")
parser.add_argument("--three_d", help="three_d",
                    action="store_true")
parser.add_argument("--headerless", help="headerless in feature file?",
                    action="store_true")

args = parser.parse_args()

if args.input == None:
	print('please specify an input meta file')
	exit(1)

meta_file = open(args.input, "r")
f_idx = args.feat_idx
n_cc = args.n_cc

max_t_steps = args.max_time_steps
input_dim = -1
feat_delim = args.feat_delim
context_length = args.context_length
half_length = int(context_length / 2)

#parsing 
count = -1
lines = []

for line in meta_file:
	line = line.rstrip()
	if count == -1:
		count = count + 1
		continue
	params = line.split('\t')
	if input_dim == -1:
		feat_file = params[f_idx]
		if args.base_dir:
			feat_file = args.base_dir + feat_file

		feat_data = np.genfromtxt (feat_file, delimiter=feat_delim)
		if len(feat_data.shape) == 1:
			input_dim = 1
		else:
			input_dim = feat_data.shape[1]
	
	lines.append(line)
	count = count + 1

#randomise	
if n_cc == 0:
	random.shuffle(lines)

n_samples = count

labels = args.multitasks.split(':')
n_labels = len(labels)

max_t_steps = int(max_t_steps / context_length)

#decide a feature structure
if args.two_d:
	X = np.zeros((n_samples, max_t_steps, 1, context_length, input_dim))
elif args.three_d:
	X = np.zeros((n_samples, 1, max_t_steps, context_length, input_dim))
else:
	X = np.zeros((n_samples, max_t_steps, input_dim * context_length))

Y = np.zeros((n_samples, n_labels))

indice_map = {}

print('input dim: ' + str(input_dim))
print('number of samples: '+ str(n_samples))
print('number of labels: '+ str(n_labels))
print('max steps: '+ str(max_t_steps))
print('context windows: '+ str(context_length))
print('half length', half_length)
print('shape', X.shape)
#actual parsing
meta_file.seek(0)
idx = 0

for line in lines:
	line = line.rstrip()
	params = line.split('\t')
	#feature file
	feat_file = params[f_idx]

	if args.base_dir:
		feat_file = args.base_dir + feat_file
    #load each feature file
	feat_data = np.genfromtxt (feat_file, delimiter=feat_delim)
	cid = int(params[args.c_idx])
	indice = indice_map.get(cid)
    # store utterance id for each cross-validation group
	if indice == None:
		indice = [idx]
		indice_map[cid] = indice
	else:
		indice.append(idx)

	#2d with context windows
	if args.two_d:
		for t_steps in range(max_t_steps):
			if t_steps * context_length < feat_data.shape[0] - context_length:
				if input_dim != 1 and feat_data.shape[1] != input_dim:
					print('inconsistent dim: ', feat_file)
					break
				for c in range(context_length):
					X[idx, t_steps, 0, c, ] = feat_data[t_steps * context_length + c]
	elif args.three_d:#3d with context windows
		for t_steps in range(max_t_steps):
			if t_steps * context_length < feat_data.shape[0] - context_length:
				if input_dim != 1 and feat_data.shape[1] != input_dim:
					print('inconsistent dim: ', feat_file)
					break
				for c in range(context_length):
					X[idx, 0, t_steps, c, ] = feat_data[t_steps * context_length + c]
	##1d but context windows copy features into time slots
	elif context_length == 1:
		for t_steps in range(max_t_steps):
			if t_steps < feat_data.shape[0]:
				if input_dim != 1 and feat_data.shape[1] != input_dim:
					print('inconsistent dim: ', feat_file)
					break
				X[idx, t_steps,] = feat_data[t_steps]
	else:#1d but context windows
		for t_steps in range(max_t_steps):
			if t_steps * context_length < feat_data.shape[0] - context_length:
				if input_dim != 1 and feat_data.shape[1] != input_dim:
					print('inconsistent dim: ', feat_file)
					break
				for c in range(context_length):
					X[idx, t_steps, c * input_dim: (c + 1) * input_dim] = feat_data[t_steps * context_length + c]
	#copy labels
	for lab_idx in range(n_labels):
		Y[idx, lab_idx] = params[int(labels[lab_idx])]
	
	idx = idx + 1
	print("processing: ", idx, " :", feat_file)


print('successfully write samples: ' + str(idx))

h5_output = args.output + '.h5'


if n_cc > 0:
	idx = 0
	# loading and constructing each fold in memory takes too much time.
	index_list = []
	start_indice = np.zeros((n_cc))
	end_indice = np.zeros((n_cc))

	if args.two_d:
		X_ordered = np.zeros((n_samples, max_t_steps, 1, context_length, input_dim))
	elif args.three_d:
		X_ordered = np.zeros((n_samples, 1, max_t_steps, context_length, input_dim))
	else:
		X_ordered = np.zeros((n_samples, max_t_steps, input_dim * context_length))
	
	Y_ordered = np.zeros((n_samples, n_labels))

	start_idx = 0
	end_idx = 0
	for cid, indice in indice_map.items():
		#print('indice', indice)
		if indice == None:
			continue
		X_temp = X[indice]
		Y_temp = Y[indice]
		end_idx = start_idx + X_temp.shape[0]
		print('shape', X_temp.shape)
		start_indice[idx] = start_idx
		end_indice[idx] = end_idx
		print("corpus: ", idx, " starting from: ", start_idx, " ends: ", end_idx)
		X_ordered[start_idx:end_idx] = X_temp
		Y_ordered[start_idx:end_idx] = Y_temp
		start_idx = end_idx
		idx = idx + 1
		
	print("shape of feat: ", X_ordered.shape)
	print("shape of label: ", Y_ordered.shape)
	with h5py.File(h5_output, 'w') as hf:
		hf.create_dataset('feat', data= X_ordered)
		hf.create_dataset('label', data= Y_ordered)
		hf.create_dataset('start_indice', data=start_indice)
		hf.create_dataset('end_indice', data=end_indice)
	print('total cv: ' + str(len(start_indice)))	
	'''
	with h5py.File(h5_output, 'w') as hf:
		hf.create_dataset('feat', data=X)
		hf.create_dataset('label', data=Y)'''
else:
	print("shape of feat: ", X.shape)
	print("shape of label: ", Y.shape)
	with h5py.File(h5_output, 'w') as hf:
		hf.create_dataset('feat', data=X)
		hf.create_dataset('label', data=Y)

meta_file.close()
