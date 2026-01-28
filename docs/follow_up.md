# Follow Up Details

- [`Dependency Tier`](../src/types/dependency_tier.py) as it is currently provides a pretty vertically limited space to group dependencies, switching to an A-Z would provide at least 26 values of verticality and provide a bit more flexibility in the structure

- [`Condition Index`](../src/models/condition_index.py) implements a not discussed interpretation which averages a containing model's condition index based on the average of its component model instances. I.e. a Facility.index_condition is the mean average of all of the underyling System.index_condition.

  - There is no weighting in these calculations - just pure mean. With a `Facility.mission_criticality` in the `Installation` calculation there is the opportunity to use these as a weighting on the calculation. 

  - The value of the simulated condition indeces is not in any way correlated to the    life_expectancy or age. It seems easy to assume that if a bit of infra is older it would be more likely to not have a pristine index value, but this is not represented in the provided axiom.