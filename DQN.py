import keras
import numpy as np

class DeepQLearning(object):
    def __init__(self, env, 
                       gamma, 
                       model_type='mlp', 
                       action_space_map = None,
                       num_iterations = 5000, 
                       sample_every_N_transitions = 10,
                       batchsize = 1000,
                       copy_over_target_every_M_training_iterations = 100,
                       max_time_spent_in_episode = 100,
                       buffer_size = 10000,
                       num_frame_stack=1,
                       min_buffer_size_to_train=1000,
                       ):
        self.env = env
        self.num_iterations = num_iterations
        self.gamma = gamma
        self.buffer = Buffer(buffer_size=buffer_size, num_frame_stack=num_frame_stack, min_buffer_size_to_train=min_buffer_size_to_train)
        self.sample_every_N_transitions = sample_every_N_transitions
        self.batchsize = batchsize
        self.copy_over_target_every_M_training_iterations = copy_over_target_every_M_training_iterations
        self.max_time_spent_in_episode = max_time_spent_in_episode
        self.action_space_map = action_space_map

    def min_over_a(self, *args, **kw):
        return self.Q.min_over_a(*args, **kw)

    def all_actions(self, *args, **kw):
        return self.Q.all_actions(*args, **kw)

    def learn(self):
        
        self.time_steps = 0
        training_iteration = -1
        costs = []
        for i in range(self.num_iterations):
            x = self.env.reset()
            self.buffer.start_new_episode(x)
            done = False
            time_spent_in_episode = 0
            episode_cost = 0
            while not done:
                # if (i % 10 == 0): self.env.render()
                time_spent_in_episode += 1
                self.time_steps += 1
                # print time_spent_in_episode

                action = self.Q(self.buffer.current_state())[0]
                if np.random.rand(1) < self.epsilon(i):
                    action = self.sample_random_action()
                
                x_prime , cost, done, _ = self.env.step(self.action_space_map[action])
                done = done or self.env.is_early_episode_termination(cost[0])
                
                # self.buffer.append([x,action,x_prime, cost[0], done])
                
                self.buffer.append(action, x_prime, cost[0], done)

                # train
                is_train = ((self.time_steps % self.sample_every_N_transitions) == 0) and self.buffer.is_enough()

                if is_train:
                    # for _ in range(len(self.buffer.data)/self.sample_every_N_transitions):
                    training_iteration += 1
                    if (training_iteration % self.copy_over_target_every_M_training_iterations) == 0: 
                        self.Q.copy_over_to(self.Q_target)
                    batch_x, batch_a, batch_x_prime, batch_cost, batch_done = self.buffer.sample(self.batchsize)

                    target = batch_cost + self.gamma*self.Q_target.min_over_a(np.stack(batch_x_prime))[0]*(1-batch_done)
                    X = [batch_x, batch_a]
                    
                    evaluation = self.Q.fit(X,target,epochs=1, batch_size=32,evaluate=False,verbose=False,tqdm_verbose=False)
                
                x = x_prime

                episode_cost += cost[0]
            costs.append(episode_cost/self.env.min_cost)

            if (i % 1) == 0:
                print 'Number of frames seen: %s' % self.time_steps
                print 'Iteration %s performance: %s. Average performance: %s' % (i, costs[-1], np.sum(costs[-200:])/200.)
            if (np.sum(costs[-200:])/200.) >= .85:
                return

    def __call__(self,*args):
        return self.Q.__call__(*args)

# class Buffer(object):
#     def __init__(self, buffer_size=10000):
#         self.data = []
#         self.size = buffer_size
#         self.idx = -1

#     def append(self, datum):
#         self.idx = (self.idx + 1) % self.size
        
#         if len(self.data) > self.idx:
#             self.data[self.idx] = datum
#         else:
#             self.data.append(datum)

#     def sample(self, N):
#         N = min(N, len(self.data))
#         rows = np.random.choice(len(self.data), size=N, replace=False)
#         return np.array(self.data)[rows]


class Buffer(object):
    """
    This saves the agent's experience in windowed cache.
    Each frame is saved only once but state is stack of num_frame_stack frames

    In the beginning of an episode the frame-stack is padded
    with the beginning frame
    """

    def __init__(self,
            num_frame_stack=1,
            buffer_size=10000,
            min_buffer_size_to_train=1000,
    ):
        self.num_frame_stack = num_frame_stack
        self.capacity = buffer_size
        self.counter = 0
        self.frame_window = None
        self.max_frame_cache = self.capacity + 2 * self.num_frame_stack + 1
        self.init_caches()
        self.expecting_new_episode = True
        self.min_buffer_size_to_train = min_buffer_size_to_train

    def append(self, action, frame, reward, done):
        assert self.frame_window is not None, "start episode first"
        self.counter += 1
        frame_idx = self.counter % self.max_frame_cache
        exp_idx = (self.counter - 1) % self.capacity

        self.prev_states.insert(exp_idx, self.frame_window)
        self.frame_window = np.append(self.frame_window[1:], frame_idx)
        self.next_states.insert(exp_idx, self.frame_window)
        self.actions.insert(exp_idx, action)
        self.is_done.insert(exp_idx, done)
        self.frames.insert(frame_idx, frame)
        self.rewards.insert(exp_idx, reward)
        if done:
            self.expecting_new_episode = True

    def start_new_episode(self, frame):
        # it should be okay not to increment counter here
        # because episode ending frames are not used
        assert self.expecting_new_episode, "previous episode didn't end yet"
        frame_idx = self.counter % self.max_frame_cache
        self.frame_window = np.repeat(frame_idx, self.num_frame_stack)
        self.frames.insert(frame_idx, frame)
        self.expecting_new_episode = False

    def sample(self, N):
        count = min(self.capacity, self.counter)
        batchidx = np.random.randint(count, size=N)

        x = np.array(self.frames)[np.array(self.prev_states)[batchidx]]
        action = np.array(self.actions)[batchidx]
        x_prime = np.array(self.frames)[np.array(self.next_states)[batchidx]]
        reward = np.array(self.rewards)[batchidx]
        done = np.array(self.is_done)[batchidx]
        
        return [x, action, x_prime, reward, done]
            
    def is_enough(self):
        return len(self.frames) > self.min_buffer_size_to_train

    def current_state(self):
        # assert not self.expecting_new_episode, "start new episode first"'
        assert self.frame_window is not None, "do something first"
        return np.array(self.frames)[self.frame_window]

    def init_caches(self):
        self.rewards = []
        self.prev_states = []
        self.next_states = []
        self.is_done = []
        self.actions = []
        self.frames = []



