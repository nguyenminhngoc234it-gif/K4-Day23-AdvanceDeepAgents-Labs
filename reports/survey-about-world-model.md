# Survey on World Models in Artificial Intelligence and Cognitive Sciences

## TL;DR
- World models are internal predictive representations of environment dynamics used in AI and cognitive science to enable planning, reasoning, and action [1][2].
- Architecturally, world models combine deep learning methods such as VAEs, RNNs, and GANs, trained via supervised, unsupervised, and reinforcement learning, often simulating "dream" environments [3][4][5][6].
- World models improve AI applications by enhancing sample efficiency and generalization in reinforcement learning, enabling long-horizon planning and robotics control through learned simulators [7][8][9][10][11].
- Cognitive neuroscience highlights that biological world models are grounded in active environmental interaction, contrasting with current AI models trained largely passively, exposing important challenges in embodiment and grounding [12][13].
- Open problems include addressing hallucinations, handling distributional shifts, bridging passive AI training with embodied cognition, improving generalization, and unifying AI and biological world model theories.

## Background
World models are computational or neural representations that internally simulate an environment's dynamics, including physical, causal, and temporal relationships, to predict future states in response to actions. The concept originated in the 1990s within AI machine learning, notably through Schmidhuber's work on recurrent neural networks predicting future states [1]. Recent revivals and expansions by researchers such as David Ha and Yann LeCun have cast world models as central predictive architectures for autonomous agents, differing significantly from simple pattern recognition by modeling environment physics and causality [1][2]. Cognitive science frameworks, including Marr's levels of analysis, help describe the computational, algorithmic, and implementation aspects of world models across biological and artificial systems [2].

## Architectures and Methods
World models in AI predominantly use deep learning architectures that compress high-dimensional observations into latent spaces, with temporal dynamics modeled via recurrent neural networks or similar structures [3][4]. Variational Autoencoders (VAEs) provide probabilistic latent encodings well-suited for dynamics prediction, while Generative Adversarial Networks (GANs) contribute to high-fidelity sample generation [5]. Training regimes span supervised, unsupervised, self-supervised, and reinforcement learning [3][4]. Recent research explores integrating world models with Vision-Language Models (VLMs) for richer spatial-temporal context and using dropout techniques to improve generalization from simulation to real tasks [14].

## Applications
World models significantly advance reinforcement learning by serving as learned simulators that reduce reliance on costly real-world interactions, boosting sample efficiency and supporting policy evaluation and planning through simulations [7][8]. In robotics, world models enable foresight, imagination-driven planning via rollouts, and data amplification by synthesizing interaction data, contributing to enhanced generalization and sample efficiency in embodied AI tasks [8][10]. Planning algorithms like Monte Carlo Tree Search and Model Predictive Control, combined with action-conditioned visual world models, facilitate long-horizon planning in raw sensory spaces, outperforming behavior cloning baselines [11]. Pretraining generalist world models on large datasets further improves reinforcement learning efficiency across diverse tasks, although challenges remain in bridging offline pretraining with online fine-tuning to prevent distribution shifts [9].

## Cognitive and Neuroscience Perspectives
Biological organisms build grounded world models through active interaction with their environment, which scaffold language and cognition. This contrasts with current AI models often trained passively on static data, highlighting a gap in embodiment and grounded cognition [13]. Neural parallels between large language models and human cognition, such as concept cells and cognitive maps, have been observed, but measurement confounds cloud interpretations, necessitating careful audit of methodologies [12]. Bridging these differences and developing truly embodied AI with grounded world models remains a key open problem, alongside refining neuroscientific measurement techniques to validate cognitive and neural analogies in artificial models.

## Trends and Open Problems
Recent trends include combining world models with vision-language models to enhance spatial and temporal understanding and employing dropout-based methods to improve simulation-to-reality generalization. Open challenges are the mitigation of hallucination phenomena in world model predictions, handling distributional shifts in pretraining and fine-tuning, and achieving true embodiment and grounding in AI comparable to biological systems. Additionally, unifying AI architectures for world models with cognitive and neuroscientific theories continues to attract research, aiming to bridge artificial and natural intelligence in a principled manner.

This survey consolidates a rich, multidisciplinary understanding of world models as a foundational and active research area in AI and cognitive sciences.

## References
[1] World model (artificial intelligence) - Wikipedia. web. https://en.wikipedia.org/wiki/World_model_(artificial_intelligence) (2026-10-06)
[2] World-models, artificial general intelligence, and the sciences of the mind. web. https://royalsocietypublishing.org/rsta/article/384/2320/20240533/481677/World-models-artificial-general-intelligence-and (2026-05-14)
[3] Understanding World or Predicting Future? A Comprehensive Survey of World Models. hf-search. https://huggingface.co/papers/2411.14499 (2024-11-21)
[4] World Models. hf-search. https://huggingface.co/papers/1803.10122 (2018-03-27)
[5] Deep Generative Modelling: A Comparative Review of VAEs, GANs, Normalizing Flows, Energy-Based and Autoregressive Models. hf-search. https://huggingface.co/papers/2103.04922 (2021-03-08)
[6] Dropout's Dream Land: Generalization from Learned Simulators to Reality. hf-search. https://huggingface.co/papers/2109.08342 (2021-09-17)
[7] World Models as an Intermediary between Agents and the Real World. web. https://arxiv.org/pdf/2602.00785v1 (n.d.)
[8] World Model for Robot Learning: A Comprehensive Survey. web. https://arxiv.org/html/2605.00080v1 (n.d.)
[9] Generalist World Model Pre-Training for Efficient Reinforcement Learning. web. https://ar5iv.labs.arxiv.org/html/2502.19544 (n.d.)
[10] What Is a World Model? | NVIDIA Glossary. web. https://www.nvidia.com/en-us/glossary/world-models/ (n.d.)
[11] WorldPlanner: Monte Carlo Tree Search and MPC with Action-Conditioned Visual World Models. web. https://arxiv.org/html/2511.03077 (n.d.)
[12] When Is a Steerable Concept Representation Real? Measurement Confounds in a Cross-Family Audit of Neuroscience Parallels in LLMs. arxiv. https://arxiv.org/abs/2608.08159 (2026-08-08)
[13] Grounded world models in biological organisms and future embodied AI. arxiv. https://arxiv.org/abs/2607.13560 (2026-07-15)
[14] Can World Models Benefit VLMs for World Dynamics?. hf-search. https://huggingface.co/papers/2510.00855 (2025-10-01)
