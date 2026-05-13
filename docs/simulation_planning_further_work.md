# Simulation Plan

MIDAS is built to provide the ability to easily author modules which can be integrated into the simulation to effect how it behaves and interact with the underlying data/domain. This document outlines and summarizes the modules and work on the simulation which had been planned and explored but remain incomplete as of the conclusion of DMR (Spring) 2026 program.

## Planned Modules Outline

### 1. Use Factor

Define different bands of 'use-factor' for individual System Type instances by adding an attribute reflects the nature of how a System Type is used in the course of its life. For example:

- A System Type which is always on would not suffer any degradation from startup/shutdown power cycling, an activity which is notorious for its degradation effect on equipment. However, due to the nature of it always being on (24/7) there may be a more consistent effect over time, or it may be seen as a more curcial piece of infrastructure for a given Facility/Installation.
- A System Type which is used very occassionally or is shut off after every use would not be as likely to suffer a continuous degradation over time.

Possible categories of Use:

1. Always On - 24/7 functionality/usage
2. Occassional - Define some parameter/periodicity for occasional
3. Working Hours - Follow a 9-5/5 day a week use cycle
4. Rare/Incidental - Rarely used through the course of the year

There was no work created for this module which was ever made viewable/referenceable.

### 2. Major Event

Define different major events which might externally effect infrastructure in some major operational capacity. Examples included discussions about: Weather Events (Tornadoes, Hurricanes), Adversarial Attacks (Hacking, Physical Penetration, Subtrafuge/Sabatoge), Power Outages, etc. Some of this may cross over with the intended 'Location' based module and would rely on historical regional data to determine event likelehoods/types.

There was no work submitted for this module which was ever made viewable/referenceable.

### 3. Work Order

Initial work has been done on this module see [work_order_progression.py](../src/simulation/modules/work_order_progression.py) to first understand the current state. Originally the module was intended to be much more complete in scope but this work was incomplete at the time of project closure.

Work Order data is a great indicator of the state of infrastructure and can be used to extrapolate and infer a lot of detail about it. There were a number of features discussed and outlined as possible parts of this module:

1. Work Order Creation: Should create and update System's with new Work Orders as the simulation progresses. Rates should and other internal constants should be configureable in the settings, but likely should follow a typical Bathtup Curve pattern based on the expected life of a System (based on the underlying System Type).
2. Work Order Status: Incomplete Work Orders effect should compound over time left unaddressed at configureable rates. Similarly completed Work Orders could potentially 'repair' the condition index of a System or at a minimum stop the compounding effects of open Work Orders.
3. Work Order Magnitude: The scope of the work being completed, urgency, priority, and Work Type (Trade) could behave differnetly in a according to percieved severity.

### 4. Enviornment

A category of module which address geographic/locational effects on Infrastructure.

#### A. Location

Considerations for locationally dependant effects which might be unique to the specific region or location of Infrastructure. Work was started on this module but it was not written following the 'Module' conventions and non-integratable/incomplete at the time of project completion. That work can be found on the [cond_ind_formulat_vedant](https://github.com/horaciovelvetine/midas-alt/tree/cond_ind_formula_vedant) branch.

#### B. Weather

The intention was to use weather data from [open-meteo](https://open-meteo.com/) in conjunction with the coordinates of an Installation location to create a historical record of a locations weather to infer how that weather would potentially effect the condition of the underlying infrastrucuute. Significant work was done on the [weather_predictions](https://github.com/horaciovelvetine/midas-alt/tree/weather_predictions) branch of the repo in the [Weather T1](https://github.com/horaciovelvetine/midas-alt/tree/weather_predictions/src/simulation/Weather-T1) directory, but the code was authored by AI with no use or reference of the module integration or plan to do so. Instead it is written as a complete individual python project which is completely un-reviewed and un-integrated into the MIDAS application.

## Hazard/Weibull Analysis Integration

Outside of the planned modules there is another repository: [hazard-analysis-weibull](https://github.com/horaciovelvetine/hazard-analysis-weibull) which contains a conceptual plan for integrating weibull hazard analysis as a means of scoring and evaluating the performance of the simulation itself. Significant documentation is included in this repo which contains a plan for integration into MIDAS in the future, as well as detailed implementation plans. A copy of this repo has been zipped and included in the [docs/hazard-weibull-analysis](../docs/hazard-weibull-analysis/hazard-analysis-weibull-main.zip) folder as a part of this repo.

## Bulk Run Simulations

MIDAS was being built towards the idea that many paralell iterations of simulations could be run on the same initial data in large batches to determine the most likely outcomes. The architecture of the application is written with this future implementation in mind, but in the limited time of the project this goal was not started on in any shape.

## Test Coverage Follow-ups

A targeted coverage pass on top of the post-refactor baseline (~67%) raised overall line coverage to **~87%** across the shipping `src/` tree. The remaining gaps are intentional and live in code that is either terminal-bound, render-heavy, or boilerplate. Future work should weigh the cost of mocking these surfaces against the regression risk before adding tests.