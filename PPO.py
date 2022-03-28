from torch.distributions import MultivariateNormal
from torch.optim import Adam

class PPO:

  def __init__(self, env):

    self.env = env
    self.obs_dim = env.observation_space.shape[0]
    self.act_dim = env.action_space.shape[0]

    self.actor = FFNN(self.obs_dim, self.act_dim)
    self.critic = FFNN(self.obs_dim, self.act_dim)

    self._init_hyperparameters()

    self.actor_optim = Adam(self.actor.parameters(), lr=self.lr)
    self.critic_optim = Adam(self.critic.parameters(), lr=self.lr)

    self.cov_var = torch.full(size=(self.act_dim,), fill_value=0.5)
    self.cov_mat = torch .diag(self.cov_var)

  def _init_hyperparameters(self):
    self.steps_per_batch = 4800
    self.max_steps_per_episode = 1600
    self.gamma = 0.95
    self.n_updates_per_iteration = 5
    self.clip = 0.2
    self.lr = 0.005

  def learn(self, max_steps): 
    step = 0

    while step < max_steps:
      batch_obs, batch_acts, batch_log_probs, batch_rtgs, batch_lens = self.rollout()

      step += np.sum(batch_lens)

      V, _ = self.evaluate(batch_obs, batch_acts)

      A_k = batch_rtgs - V.detach()

      A_k = (A_k - A_k.mean()) / (A_k.std() + 1e-10)     

      for _ in range(self.n_updates_per_iteration):

        V, curr_log_probs = self.evaluate(batch_obs, batch_acts)

        ratio = torch.exp(curr_log_probs - batch_log_probs)

        surr1 = ratio * A_k
        surr2 = torch.clamp(ratio, 1 - self.clip, 1 + self.clip) * A_k

        actor_loss = (-torch.min(surr1, surr2)).mean()
        critic_loss = nn.MSELoss()(V, batch_rtgs)

        self.actor_optim.zero_grad()
        actor_loss.backward(retain_graph=True)
        self.actor_optim.step() 

        self.critic_optim.zero_grad()
        critic_loss.backward()
        self.critic_optim.step()

  def get_action(self, obs):

    mean = self.actor(obs)
    dist = MultivariateNormal(mean, self.cov_mat)

    action = dist.sample()
    log_prob = dist.log_prob(action)

    return action.detach().numpy(), log_prob.detach()

  def rollout(self):
    batch_obs = []
    batch_acts = []
    batch_log_probs = []
    batch_rews  =[]
    batch_rtgs = []
    batch_lens = []

    step = 0
    while step < self.steps_per_batch:

      ep_rews = []
      obs = self.env.reset()
      done = False

      for ep_t in range(self.max_steps_per_episode):
        step += 1
        batch_obs.append(obs)

        action, log_prob = self.get_action(obs)
        obs, rew, done, _ = self.env.step(action)

        ep_rews.append(rew)
        batch_acts.append(action)
        batch_log_probs.append(log_prob)

        if done:
          break

      batch_lens.append(ep_t + 1)
      batch_rews.append(ep_rews)

    batch_obs = torch.tensor(batch_obs, dtype=torch.float)
    batch_acts = torch.tensor(batch_acts, dtype=torch.float)
    batch_log_probs = torch.tensor(batch_log_probs, dtype=torch.float)

    batch_rtgs = self.compute_rtgs(batch_rews)

    return  batch_obs, batch_acts, batch_log_probs, batch_rtgs, batch_lens

  def compute_rtgs(self, batch_rews):

    batch_rtgs = []

    for ep_rews in reversed(batch_rews):
      discounted_reward = 0

      for rew in reversed(ep_rews):
        discounted_reward = rew + discounted_reward * self.gamma
        batch_rtgs.insert(0, discounted_reward)

    batch_rtgs = torch.tensor(batch_rtgs,  dtype=torch.float)

    return batch_rtgs

  def evaluate(self, batch_obs, batch_acts):
    V = self.critic(batch_obs).squeeze()

    mean = self.actor(batch_obs)
    dist = MultivariateNormal(mean, self.cov_mat)
    log_probs = dist.log_prob(batch_acts)

    return V, log_probs