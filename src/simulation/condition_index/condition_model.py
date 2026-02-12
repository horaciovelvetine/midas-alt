"""

Basic Template of what I've made so far, will need to update and change half of the vraiables based off the maintenance and weather stuff

Docstring for condition_model

Time-series of condition index changing over time based off the variables.

This is subject to change as the weather stress, report files, etc are going to be plugged in later as I have not created them.

Inputs per timestep:
 - weather_stress (float 0-1, will probably switch based off of what the wather formula team makes)
 - deferred_reports (list of priority levels 1-5 based off what I heard last meeting)
 - completed_reports (list of priority levels 1-5 based off what I heard last meeting)

Outputs:
 - condition index history
 - discrete condition state history
 - deferred backlog history

the imported packages and other IP will be listed below:

* numpy

* waiting on the weather formula/data
* waiting on the maintenance defer and fix stuff
* will need to add more variables later on to be as configurable as possible

"""

import numpy as np


class FacilityConditionModel:

    def __init__(
        self,
        initial_condition=100.0,
        base_aging=0.5,
        alpha_weather=5.0,
        beta_deferred=0.3,
        gamma_recovery_scale=1.0,
        noise_std=0.5
    ):
        """
        Configurable Parameters:
            initial_condition: starting condition index (0-100)
            base_aging: natural degradation per timestep
            alpha_weather: weather stress sensitivity
            beta_deferred: deferred backlog sensitivity
            gamma_recovery_scale: multiplier on recovery amounts
            noise_std: Gaussian noise std deviation
        """

        self.condition = initial_condition
        self.base_aging = base_aging
        self.alpha_weather = alpha_weather
        self.beta_deferred = beta_deferred
        self.gamma_recovery_scale = gamma_recovery_scale
        self.noise_std = noise_std

        self.deferred_backlog = 0.0

        # History of condition and state, technically not necessary for markov bc its simply based off curent state but its good to see how the state
        # changes for debug
        self.condition_history = []
        self.state_history = []
        self.backlog_history = []

    # Priority's
    def priority_weight(priority):
        """
        Maps maintenance priority (1-5) to impact weight.
        1 = Critical, 5 = Minor // Not sure if this is true, its really just based off what the team has been priortizing
        """
        weight_map = {
            1: 20,
            2: 15,
            3: 10,
            4: 5,
            5: 2
        }
        return weight_map.get(priority, 0)

    # Discrete condition state
    def condition_to_state(condition):
        if condition >= 80:
            return "Healthy"
        elif condition >= 60:
            return "Minor"
        elif condition >= 40:
            return "Moderate"
        elif condition >= 20:
            return "Severe"
        else:
            return "Failed"

    # Single timestep update
    def step(self, weather_stress, deferred_reports, completed_reports):
        """
        weather_stress: float (0-1)
        deferred_reports: list of priority ints
        completed_reports: list of priority ints
        """

        # Update deferred backlog, will update to what the reports team has been working on later
        for priority in deferred_reports:
            self.deferred_backlog += self.priority_weight(priority)

        # Compute recovery, for if a system gets fixed or deferred
        recovery = sum(self.priority_weight(p) for p in completed_reports)
        recovery *= self.gamma_recovery_scale

        self.deferred_backlog = max(
            0.0,
            self.deferred_backlog - recovery
        )

        # Main degredation stuff to compute degradation
        degradation = (
            self.base_aging
            + self.alpha_weather * weather_stress
            + self.beta_deferred * self.deferred_backlog
        )

        noise = np.random.normal(0, self.noise_std)

        # The formula I've made so far condition update equation
        self.condition = (
            self.condition
            - degradation
            + recovery
            + noise
        )

        # Condition index is from 0 to 100
        self.condition = max(0.0, min(100.0, self.condition))

        self.condition_history.append(self.condition)
        self.backlog_history.append(self.deferred_backlog)
        self.state_history.append(
            self.condition_to_state(self.condition)
        )

    # Run full time series
    def run(self, weather_series, deferred_series, completed_series):
        """
        All inputs must be same length lists.
        """

        n = len(weather_series)

        for t in range(n):
            self.step(
                weather_series[t],
                deferred_series[t],
                completed_series[t]
            )

        return {
            "condition_history": self.condition_history,
            "state_history": self.state_history,
            "backlog_history": self.backlog_history
        }