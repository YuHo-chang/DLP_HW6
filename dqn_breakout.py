'''DLP DQN Lab'''
__author__ = 'chengscott'
__copyright__ = 'Copyright 2020, NCTU CGI Lab'
import argparse
from collections import deque
import itertools
import random
import time
from tqdm import tqdm

import gym
import numpy as np
import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
from atari_wrappers import wrap_deepmind, make_atari


class ReplayMemory(object):
    ## TODO ##
    __slots__ = ['buffer']
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, *transition):
        """Saves a transition"""
        self.buffer.append(tuple(map(tuple, transition)))        

    def sample(self, batch_size, device):
        """Sample a batch of transitions"""
        transitions = random.sample(self.buffer, batch_size)
        return (torch.tensor(x, dtype=torch.float, device=device)
                for x in zip(*transitions))
        

    def __len__(self):
        return self.size


class Net(nn.Module):
    def __init__(self, num_classes=4, init_weights=True):
        super(Net, self).__init__()

        self.cnn = nn.Sequential(nn.Conv2d(4, 32, kernel_size=8, stride=4),
                                        nn.ReLU(True),
                                        nn.Conv2d(32, 64, kernel_size=4, stride=2),
                                        nn.ReLU(True),
                                        nn.Conv2d(64, 64, kernel_size=3, stride=1),
                                 nn.ReLU(True)
                                        )
        self.classifier = nn.Sequential(nn.Linear(7*7*64, 512),
                                        nn.ReLU(True),
                                        nn.Linear(512, num_classes)
                                        )
        if init_weights:
            self._initialize_weights()

    def forward(self, x):
        x = x.float() / 255.
        x = self.cnn(x)
        x = torch.flatten(x, start_dim=1)
        x = self.classifier(x)
        return x

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
            elif isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                nn.init.constant_(m.bias, 0.0)


class DQN:
    def __init__(self, args):
        self._behavior_net = Net().to(args.device)
        self._target_net = Net().to(args.device)
        # initialize target network
        self._target_net.load_state_dict(self._behavior_net.state_dict())
        self._target_net.eval()
        self._optimizer = torch.optim.Adam(self._behavior_net.parameters(), lr=args.lr, eps=1.5e-4)

        ## TODO ##
        """Initialize replay buffer"""
        self._memory = ReplayMemory(args.capacity)

        ## config ##
        self.device = args.device
        self.batch_size = args.batch_size
        self.gamma = args.gamma
        self.freq = args.freq
        self.target_freq = args.target_freq
    
    # def state_initialize(self):
    #     self.state_buffer = []
    #     state = self.env.reset()
    #     for _ in range(4+1):
    #         self.state_buffer.append(state)
    #     return self.state_buffer[1:5]

    def select_action(self, state, epsilon, action_space):
        '''epsilon-greedy based on behavior network'''
        ## TODO ##
        if random.random() < epsilon:
            return action_space.sample()
        
        with torch.no_grad():
            state = torch.tensor(state, device=self.device).unsqueeze(0).permute(0,3,1,2)
            outputs = self._behavior_net(state)
            _, best_action = torch.max(outputs, 1)
            return best_action.item()
        

    def append(self, state, action, reward, next_state, done):
        ## TODO ##
        """Push a transition into replay buffer"""
        self._memory.push(state, [action], [reward], next_state, [int(done)])

    def update(self, total_steps):
        if total_steps % self.freq == 0:
            self._update_behavior_network(self.gamma)
        if total_steps % self.target_freq == 0:
            self._update_target_network()

    def _update_behavior_network(self, gamma):
        # sample a minibatch of transitions
        state, action, reward, next_state, done = self._memory.sample(self.batch_size, self.device)
        ## TODO ##
        state = state.permute(0,3,1,2)
        next_state = next_state.permute(0, 3, 1, 2)
        # next_state = torch.tensor(next_state,device=self.device).permute(0, 3, 1, 2)

        q_value =self._behavior_net(state).gather(1, action.long())
        with torch.no_grad():
            q_next = torch.max(self._target_net(next_state), 1)[0].view(-1, 1)
            q_target = reward +q_next * gamma * (1 - done)
        criterion = nn.MSELoss()
        loss = criterion(q_value, q_target)

        self._optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self._behavior_net.parameters(), 5)
        self._optimizer.step()

    def _update_target_network(self):
        '''update target network by copying from behavior network'''
        ## TODO ##
        self._target_net.load_state_dict(self._behavior_net.state_dict())
        

    def save(self, model_path, checkpoint=False):
        if checkpoint:
            torch.save({
                'behavior_net': self._behavior_net.state_dict(),
                'target_net': self._target_net.state_dict(),
                'optimizer': self._optimizer.state_dict(),
            }, model_path)
        else:
            torch.save({
                'behavior_net': self._behavior_net.state_dict(),
            }, model_path)

    def load(self, model_path, checkpoint=False):
        model = torch.load(model_path)
        self._behavior_net.load_state_dict(model['behavior_net'])
        if checkpoint:
            self._target_net.load_state_dict(model['target_net'])
            self._optimizer.load_state_dict(model['optimizer'])

def train(args, agent, writer):
    print('Start Training')
    env_raw = make_atari('BreakoutNoFrameskip-v4')
    env = wrap_deepmind(env_raw, episode_life=True, clip_rewards=True, frame_stack=True)
    action_space = env.action_space
    total_steps, epsilon = 0, 1.
    if args.resume != 0:
        epsilon = args.eps_min
    ewma_reward = 0
    best_reward = -np.inf
    start_ep = args.resume
    for episode in tqdm(range(start_ep, args.episode)):
        total_reward = 0
        state = env.reset()
        state, reward, done, _ = env.step(1) # fire first !!!
        # print("start")
        for t in itertools.count(start=1):
            if total_steps < args.warmup and args.resume == 0:
                action = action_space.sample()
            else:
                # select action
                action = agent.select_action(state, epsilon, action_space)
                # decay epsilon
                epsilon -= (1 - args.eps_min) / args.eps_decay
                epsilon = max(epsilon, args.eps_min)

            # execute action
            prev_state = state
            state, reward, done, _ = env.step(action)

            ## TODO ##
            # store transition
            agent.append(prev_state, action, reward, state, done)

            if total_steps >= args.warmup:
                agent.update(total_steps)

            total_reward += reward


            total_steps += 1
            if done:
                ewma_reward = 0.05 * total_reward + (1 - 0.05) * ewma_reward
                writer.add_scalar('Train/Episode Reward', total_reward, episode)
                writer.add_scalar('Train/Ewma Reward', ewma_reward, episode)
                writer.add_scalar('Train/epsilon', epsilon, episode)
                # print('Step: {}\tEpisode: {}\tLength: {:3d}\tTotal reward: {:.2f}\tEwma reward: {:.2f}\tEpsilon: {:.3f}'
                #         .format(total_steps, episode, t, total_reward, ewma_reward, epsilon))
                break

        if episode % args.eval_freq == 0 and episode != 0:
            """You can write another evaluate function, or just call the test function."""
            val_reward = test(args, agent, writer)
            if val_reward > best_reward:
                agent.save(args.logdir + "/dqn_best" + ".pth")
                best_reward = val_reward
            agent.save(args.logdir + "/dqn_" + str(episode) + ".pth")
            writer.add_scalar('Val score', val_reward, episode)

    env.close()


def test(args, agent, writer):
    print('Start Testing')
    env_raw = make_atari('BreakoutNoFrameskip-v4')
    env = wrap_deepmind(env_raw, frame_stack=True, episode_life=False, clip_rewards=False)
    action_space = env.action_space
    e_rewards = []
    
    for i in range(args.test_episode):
        state = env.reset()
        e_reward = 0
        done = False

        while not done:
            time.sleep(0.01)
            if args.render:
                env.render()
            action = agent.select_action(state, args.test_epsilon, action_space)
            state, reward, done, _ = env.step(action)
            e_reward += reward

        e_rewards.append(e_reward)
        if args.test_only:
    #     writer.add_scalar("Val/Average Reward", float(sum(e_rewards)) / float(args.test_episode))
            print('episode {}: {:.2f}'.format(i+1, e_reward))

    env.close()
    print('Average Reward: {:.2f}'.format(float(sum(e_rewards)) / float(args.test_episode)))

    return float(sum(e_rewards)) / float(args.test_episode)

def main():
    ## arguments ##
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-d', '--device', default='cuda')
    parser.add_argument('-m', '--model', default='dqn_breakout.pth')
    parser.add_argument('--logdir', default='log/breakout')
    # train
    parser.add_argument('--warmup', default=20000, type=int)
    parser.add_argument('--episode', default=20000, type=int)
    parser.add_argument('--capacity', default=100000, type=int)
    parser.add_argument('--batch_size', default=32, type=int)
    parser.add_argument('--lr', default=0.0000625, type=float)
    parser.add_argument('--eps_decay', default=100000, type=float)
    parser.add_argument('--eps_min', default=0.1, type=float)
    parser.add_argument('--gamma', default=.99, type=float)
    parser.add_argument('--freq', default=4, type=int)
    parser.add_argument('--target_freq', default=10000, type=int)
    parser.add_argument('--eval_freq', default=500, type=int)
    parser.add_argument('--resume', default=0, type=int)
    # test
    parser.add_argument('--test_only', action='store_true', default=False)
    parser.add_argument('-tmp', '--test_model_path', default='ckpt/dqn_1000000.pt')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--test_episode', default=10, type=int)
    parser.add_argument('--seed', default=20230422, type=int)
    parser.add_argument('--test_epsilon', default=0.01, type=float)
    args = parser.parse_args()

    ## main ##
    agent = DQN(args)
    writer = SummaryWriter(args.logdir)
    if not args.test_only:
        if args.resume != 0:
            agent.load(args.logdir + "/dqn_" + str(args.resume) + ".pth")
        train(args, agent, writer)
        agent.save(args.model)
    else:
        agent.load(f"{args.logdir}/dqn_best.pth")
        test(args, agent, writer)
        


if __name__ == '__main__':
    main()
