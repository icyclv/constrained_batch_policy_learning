"""
Created on December 12, 2018

@author: clvoloshin, 
"""

from fitted_algo import FittedAlgo
import numpy as np
from tqdm import tqdm

class FittedQEvaluation(FittedAlgo):
    def __init__(self, initial_states, num_inputs, grid_shape, dim_of_actions, max_epochs, gamma,model_type='mlp'):
        '''
        An implementation of fitted Q iteration

        num_inputs: number of inputs
        dim_of_actions: dimension of action space
        max_epochs: positive int, specifies how many iterations to run the algorithm
        gamma: discount factor
        '''
        self.model_type = model_type
        self.initial_states = initial_states
        super(FittedQEvaluation, self).__init__(num_inputs, grid_shape, dim_of_actions, max_epochs, gamma)

    def run(self, dataset, policy, epochs=5000, epsilon=1e-10, desc='FQE', **kw):
        # dataset is the original dataset generated by pi_{old} to which we will find
        # an approximately optimal Q

        self.Q_k = self.init_Q(model_type=self.model_type, **kw)

        X_a = dataset['state_action']
        x_prime = dataset['x_prime']

        index_of_skim = self.skim(X_a, x_prime)
        X_a = X_a[index_of_skim]
        x_prime = x_prime[index_of_skim]
        dataset_costs = dataset['cost'][index_of_skim]
        dones = dataset['done'][index_of_skim]

        for k in tqdm(range(self.max_epochs), desc=desc):

            # {((x,a), r+gamma* Q(x',pi(x')))}
            
            if k == 0:
                # Q_0 = 0 everywhere
                costs = dataset_costs
            else:
                costs = dataset_costs + (self.gamma*self.Q_k(x_prime, policy(x_prime)).reshape(-1)*(1-dones.astype(int))).reshape(-1)


            self.fit(X_a, costs, epochs=epochs, batch_size=X_a.shape[0], epsilon=epsilon, evaluate=False, verbose=0)

            if not self.Q_k.callbacks_list[0].converged:
                print 'Continuing training due to lack of convergence'
                self.fit(X_a, costs, epochs=epochs, batch_size=X_a.shape[0], epsilon=epsilon, evaluate=False, verbose=0)


        return np.mean([self.Q_k(state, policy(state)) for state in self.initial_states])
