"""
Created on December 12, 2018

@author: clvoloshin, 
"""

import numpy as np
from copy import deepcopy
import pandas as pd

class Program(object):
    def __init__(self, C, G, constraints, action_space_dim, best_response_algorithm, online_convex_algorithm, fitted_off_policy_evaluation_algorithm, exact_policy_algorithm, lambda_bound = 1., epsilon = .01, env= None, max_iterations=None,position_of_holes=None, position_of_goals=None):
        '''
        This is a problem of the form: min_pi C(pi) where G(pi) < eta.

        dataset: list. Will be {(x,a,x',c(x,a), g(x,a)^T)}
        action_space_dim: number of dimension of action space
        dim: number of constraints
        C, G: dictionary of |A| dim vectors
        best_response_algorithm: function which accepts a |A| dim vector and outputs a policy which minimizes L
        online_convex_algorithm: function which accepts a policy and returns an |A| dim vector (lambda) which maximizes L
        lambda_bound: positive int. l1 bound on lambda |lambda|_1 <= B
        constraints:  |A| dim vector
        epsilon: small positive float. Denotes when this problem has been solved.
        env: The environment. Used for exact policy evaluation to test fittedqevaluation
        '''

        self.dataset = Dataset(constraints, action_space_dim)
        self.constraints = constraints
        self.C = C
        self.C_exact = deepcopy(C)
        self.G = G
        self.G_exact = deepcopy(G)
        self.action_space_dim = action_space_dim
        self.dim = len(constraints)
        self.lambda_bound = lambda_bound
        self.epsilon = epsilon
        self.best_response_algorithm = best_response_algorithm
        self.online_convex_algorithm = online_convex_algorithm
        self.exact_lambdas = []
        self.fitted_off_policy_evaluation_algorithm = fitted_off_policy_evaluation_algorithm
        self.exact_policy_evaluation = exact_policy_algorithm
        self.env = env
        self.prev_lagrangians = []
        self.max_iterations = max_iterations if max_iterations is not None else np.inf
        self.iteration = 0
        self.position_of_holes=position_of_holes
        self.position_of_goals=position_of_goals

    def best_response(self, lamb, **kw):
        '''
        Best-response(lambda) = argmin_{pi} L(pi, lambda) 
        '''
        dataset = deepcopy(self.dataset)
        dataset.calculate_cost(lamb)
        policy = self.best_response_algorithm.run(dataset, position_of_goals=self.position_of_goals, position_of_holes=self.position_of_holes, **kw)
        return policy

    def online_algo(self):
        '''
        No regret online convex optimization routine
        '''
        gradient = self.G.last() - self.constraints
        lambda_t = self.online_convex_algorithm.run(gradient)

        return lambda_t

    def lagrangian(self, C, G, lamb):
        # C(pi) + lambda^T (G(pi) - eta), where eta = constraints, pi = avg of all pi's seen
        return C.avg() + np.dot(lamb, (G.avg() - self.constraints))

    def max_of_lagrangian_over_lambda(self):
        '''
        The maximum of C(pi) + lambda^T (G(pi) - eta) over lambda is
        B*e_{k+1}, all the weight on the phantom index if G(pi) < eta for all constraints
        B*e_k otherwise where B is the l1 bound on lambda and e_k is the standard
        basis vector putting full mass on the constraint which is violated the most
        '''

        # Actual calc
        maximum = np.max(self.G.avg() - self.constraints)
        index = np.argmax(self.G.avg() - self.constraints) 

        if maximum > 0:
            lamb = self.lambda_bound * np.eye(1, self.dim, index)
        else:
            lamb = np.zeros(self.dim)
            lamb[-1] = self.lambda_bound

        maximum = np.max(self.G_exact.avg() - self.constraints)
        index = np.argmax(self.G_exact.avg() - self.constraints) 

        print 'Lambda maximizing lagrangian: %s' % lamb
        return self.lagrangian(self.C, self.G, lamb)

    def min_of_lagrangian_over_policy(self, lamb):
        '''
        This function evaluates L(best_response(avg_lambda), avg_lambda)
        '''
        
        # print 'Calculating best-response(lambda_avg)'
        best_policy = self.best_response(lamb, desc='FQI pi(lambda_avg)')

        # print 'Calculating C(best_response(lambda_avg))'
        dataset = deepcopy(self.dataset)
        dataset.set_cost('c')
        if not best_policy in self.C:
            C_br = self.fitted_off_policy_evaluation_algorithm.run(dataset, best_policy, desc='FQE C(pi(lambda_avg))', position_of_goals=self.position_of_goals, position_of_holes=self.position_of_holes)
        else:
            print 'FQE C(pi(lambda_avg)) already calculated'
            C_br = self.C[best_policy]
        
        # print 'Calculating G(best_response(lambda_avg))'
        if not best_policy in self.C:
            G_br = []
            for i in range(self.dim-1):
                dataset = deepcopy(self.dataset)
                dataset.set_cost('g', i)
                G_br.append(self.fitted_off_policy_evaluation_algorithm.run(dataset, best_policy, desc='FQE G_%s(pi(lambda_avg))'% i, position_of_goals=self.position_of_goals, position_of_holes=self.position_of_holes))
            G_br.append(0)
            G_br = np.array(G_br)
        else:
            print 'FQE G(pi(lambda_avg)) already calculated'
            G_br = self.G[best_policy]

        if self.env is not None:
            print 'Calculating exact C, G policy evaluation'
            exact_c, exact_g = self.exact_policy_evaluation.run(best_policy)

        print
        print 'C(pi(lambda_avg)) Exact: %s, Evaluated: %s, Difference: %s' % (exact_c, C_br, np.abs(C_br-exact_c))
        print 'G(pi(lambda_avg)) Exact: %s, Evaluated: %s, Difference: %s' % (exact_g, G_br[:-1], np.abs(G_br[:-1]-exact_g))
        print 'Mean lambda: %s' % lamb
        print 

        return C_br + np.dot(lamb, (G_br - self.constraints)), C_br, G_br, exact_c, exact_g

    def update(self, policy, iteration):
        
        #update C
        if not policy in self.C:
            dataset = deepcopy(self.dataset)
            dataset.set_cost('c')
            C_pi = self.fitted_off_policy_evaluation_algorithm.run(dataset, policy, desc='FQE C(pi_%s)' %  iteration,position_of_goals=self.position_of_goals, position_of_holes=self.position_of_holes)
            self.C.append(C_pi, policy)
            C_pi = np.array(C_pi)
        else:
            print 'FQE C(pi_%s) already calculated' %  iteration
            self.C.append(self.C[policy].tolist())
            C_pi = self.C[policy]

        #update G
        G_pis = []
        if not policy in self.G:
            for i in range(self.dim-1):        
                dataset = deepcopy(self.dataset)
                dataset.set_cost('g', i)
                G_pis.append(self.fitted_off_policy_evaluation_algorithm.run(dataset, policy, desc='FQE G_%s(pi_%s)' %  (i, iteration),position_of_goals=self.position_of_goals, position_of_holes=self.position_of_holes))
            G_pis.append(0)
            self.G.append(G_pis, policy)
            G_pis = np.array(G_pis)
        else:
            print 'FQE G(pi_%s) already calculated' %  iteration
            G_pis = self.G.append(self.G[policy].tolist())
            G_pis = self.G[policy]

        # Get Exact Policy
        
        if self.env is not None:
            print 'Calculating exact C, G policy evaluation'
            exact_c, exact_g = self.exact_policy_evaluation.run(policy)
            self.C_exact.append(exact_c)
            self.G_exact.append(np.hstack([exact_g, np.array([0])]))

        print
        print 'C(pi_%s) Exact: %s, Evaluated: %s, Difference: %s' % (iteration, exact_c, C_pi, np.abs(C_pi-exact_c))
        print 'G(pi_%s) Exact: %s, Evaluated: %s, Difference: %s' % (iteration, exact_g, G_pis[:-1], np.abs(G_pis[:-1]-exact_g))
        print 

    def collect(self, *data):
        '''
        Add more data
        '''
        self.dataset.append(*data)

    def finish_collection(self):
        # preprocess
        self.dataset.preprocess()

    def is_over(self, policies, lambdas, infinite_loop=False):
        # lambdas: list. We care about average of all lambdas seen thus far
        # If |max_lambda L(avg_pi, lambda) - L(best_response(avg_lambda), avg_lambda)| < epsilon, then done
        self.iteration += 1


        if len(lambdas) == 0: return False
        if len(lambdas) == 1: 
            #use stored values
            x = self.max_of_lagrangian_over_lambda()
            y = self.C.last() + np.dot(lambdas[-1], (self.G.last() - self.constraints))
            c_br, g_br, c_br_exact, g_br_exact = self.C.last(), self.G.last(), self.C_exact.last(), self.G_exact.last()
        else:
            x = self.max_of_lagrangian_over_lambda()
            y,c_br, g_br, c_br_exact, g_br_exact = self.min_of_lagrangian_over_policy(np.mean(lambdas, 0))

        difference = x-y
        
        c_exact, g_exact = self.C_exact.avg(), self.G_exact.avg()[:-1]
        c_approx, g_approx = self.C.avg(), self.G.avg()[:-1]

        self.prev_lagrangians.append(np.hstack([self.iteration, x, y, c_exact, g_exact, c_approx, g_approx, self.C_exact.last(), self.G_exact.last()[0], self.C.last(), self.G.last()[0], lambdas[-1][0], c_br_exact, g_br_exact[0], c_br, g_br[0]  ]))

        print 'actual max L: %s, min_L: %s, difference: %s' % (x,y,x-y)
        print 'Average policy. C Exact: %s, C Approx: %s' % (c_exact, c_approx)
        print 'Average policy. G Exact: %s, G Approx: %s' % (g_exact, g_approx)

        self.save()
        if infinite_loop:
            # Run forever to gather long curve for experiment
            return False
        else:
            if difference < self.epsilon:
                return True
            elif self.iteration >= self.max_iterations:
                return True
            else: 
                return False

    def save(self):
        df = pd.DataFrame(self.prev_lagrangians, columns=['iteration', 'max_L', 'min_L', 'c_exact_avg', 'g_exact_avg', 'c_avg', 'g_avg', 'c_pi_exact', 'g_pi_exact', 'c_pi', 'g_pi', 'lambda', 'c_br_exact', 'g_br_exact', 'c_br', 'g_br'])
        df.to_csv('experiment_results.csv', index=False)


class Dataset(object):
    def __init__(self, constraints, action_dim):
        self.data = {'x':[], 'a':[], 'x_prime':[], 'c':[], 'g':[], 'done':[], 'cost':[]}
        self.episodes = [Episode(constraints, action_dim)]
        self.constraints = constraints
        self.action_dim = action_dim
        self.max_trajectory_length = 0

    def append(self, *args):
        if not self.episodes[-1].is_over():
            self.episodes[-1].append(*args)
        else:
            self.episodes.append(Episode(self.constraints, self.action_dim))
            self.episodes[-1].append(*args)

        # update max_trajectory_length
        if self.episodes[-1].get_length() > self.max_trajectory_length:
            self.max_trajectory_length = self.episodes[-1].get_length()
        
    def get_max_trajectory_length(self):
        return self.max_trajectory_length
        
    def __getitem__(self, key):
        return np.array(self.data[key])

    def __setitem__(self, key, item):
        self.data[key] = item

    def __len__(self):
        return len(self.data['x'])

    def preprocess(self):
        for key in self.data:
            if key in ['g']:
                try:
                    self.data[key] = np.vstack([x[key] for x in self.episodes]).tolist()
                except:
                    self.data[key] = np.hstack([x[key] for x in self.episodes]).tolist()
            else:
                self.data[key] = np.hstack([x[key] for x in self.episodes]).tolist()
        [x.get_state_action_pairs() for x in self.episodes]
        self.get_state_action_pairs()

    def get_state_action_pairs(self):
        if 'state_action' in self.data:
            return self.data['state_action']
        else:
            pairs = np.vstack([np.array(self.data['x']), np.array(self.data['a']) ]).T
            self.data['state_action'] = pairs

    def calculate_cost(self, lamb):

        costs = np.array(self.data['c'] + np.dot(lamb, np.array(self.data['g']).T))

        costs = costs/np.max(np.abs(costs))
        self.data['cost'] = costs.tolist()

        [x.calculate_cost(lamb) for x in self.episodes]

    def set_cost(self, key, idx=None):
        if key == 'g': assert idx is not None, 'Evaluation must be done per constraint until parallelized'

        if key == 'c':
            self.data['cost'] = self.data['c']
            [x.set_cost('c') for x in self.episodes]
        elif key == 'g':
            # Pick the idx'th constraint
            self.data['cost'] = np.array(self.data['g'])[:,idx].tolist()
            [x.set_cost('g', idx) for x in self.episodes]
        else:
            raise


class Episode(object):
    def __init__(self, constraints, action_dim):
        self.data = {'x':[], 'a':[], 'x_prime':[], 'c':[], 'g':[], 'done':[], 'cost':[]}
        self.constraints = constraints
        self.action_dim = action_dim
        self.trajectory_length = 0

    def is_over(self):
        if len(self.data['done']):
            return self.data['done'][-1]
        else:
            return False

    def get_length(self):
        return self.trajectory_length

    def append(self, x, a, x_prime, c, g, done):
        self.data['x'].append(x)
        self.data['a'].append(a)
        self.data['x_prime'].append(x_prime)
        self.data['c'].append(c)
        self.data['g'].append(g)
        self.data['done'].append(done)
        self.trajectory_length += 1      
        
    def __getitem__(self, key):
        return np.array(self.data[key])

    def __setitem__(self, key, item):
        self.data[key] = item

    def __len__(self):
        return len(self.data['x'])

    def preprocess(self):
        self.get_state_action_pairs()

    def get_state_action_pairs(self):
        if 'state_action' in self.data:
            return self.data['state_action']
        else:
            pairs = np.vstack([np.array(self.data['x']), np.array(self.data['a'])]).T
            self.data['state_action'] = pairs

    def calculate_cost(self, lamb):
        costs = np.array(self.data['c'] + np.dot(lamb, np.array(self.data['g']).T))

        costs = costs/np.max(np.abs(costs))
        self.data['cost'] = costs.tolist()

    def set_cost(self, key, idx=None):
        if key == 'g': assert idx is not None, 'Evaluation must be done per constraint until parallelized'

        if key == 'c':
            self.data['cost'] = self.data['c']
        elif key == 'g':
            # Pick the idx'th constraint
            self.data['cost'] = np.array(self.data['g'])[:,idx].tolist()
        else:
            raise




