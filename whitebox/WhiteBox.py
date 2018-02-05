#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from functools import partial

import numpy as np
from pandas import DataFrame, concat
from pandas.api.types import is_categorical_dtype

from whitebox import utils
from whitebox_base import WhiteBoxBase

__author__ = """Jason Lewris, Daniel Byler, Venkat Gangavarapu, 
                Shruti Panda, Shanti Jha"""
__credits__ = ["Brian Ray"]
__license__ = "MIT"
__version__ = "0.0.1"
__maintainer__ = "Jason Lewris"
__email__ = "jlewris@deloitte.com"
__status__ = "Beta"


class WhiteBoxError(WhiteBoxBase):

    """
    Error model analysis.

    In the continuous case with over 100 datapoints for a particular slice of data,
    calculate percentiles of group of shrink data to 100 datapoints for scalability.
    Calculate average errors within this region of the data for positive and negative errors.

    In the categorical case, calculate average positive/negative error within region of data

    Parameters

    ----------

    modelobj : sklearn model object
        Used to create predictions for synthetic data

    model_df : pandas DataFrame
        Original raw dataset used to train and calibrate modelobj. This can
        and should in most cases include dummy variables for categorical data columns.

    ydepend : str
        Y dependent variable used to build modelobj

    cat_df : pandas DataFrame
        Raw, unadjusted dataframe with categorical columns converted to pandas
        data type Categorical. These categorical designations are picked up throughout
        and are important for proper functioning of WhiteBoxSensitvitiy

    featuredict : dict
        Optional user defined dictionary to clean up column name and subset
        the outputs to only columns defined in featuredict

    groupbyvars : list
        grouping variables to analyze impact of model for various groups of data. I.e.
        if working on dataset with red and white wine, we can disambiguate how sensitive
        the model is to changes in data for each type of wine

    aggregate_func : function
        function to perform aggregate function to groups of data pertaining to error
        analysis. I.e. take the median model error for groups data.

    verbose : int
        Logging level

    See also

    ------------

    WhiteBoxSensitivity : analyze how the model errors are doing for various groups of data
    WhiteBoxBase : base class inherited from WhiteBoxSensitivity to perform key functionality
        and grouping logic
    """

    def __init__(
                    self,
                    modelobj,
                    model_df,
                    ydepend,
                    cat_df=None,
                    featuredict=None,
                    groupbyvars=None,
                    aggregate_func=np.mean,
                    verbose=0):

        """
        :param modelobj: sklearn model object
        :param model_df: Pandas Dataframe used to build/train model
        :param ydepend: Y dependent variable
        :param cat_df: Pandas Dataframe of raw data - with categorical datatypes
        :param featuredict: Subset and rename columns
        :param groupbyvars: grouping variables
        :param aggregate_func: numpy aggregate function like np.mean
        :param verbose: Logging level
        """
        super(WhiteBoxError, self).__init__(
                                            modelobj,
                                            model_df,
                                            ydepend,
                                            cat_df=cat_df,
                                            featuredict=featuredict,
                                            groupbyvars=groupbyvars,
                                            aggregate_func=aggregate_func,
                                            verbose=verbose)

    def _transform_function(
                            self,
                            group,
                            groupby='Type',
                            col=None,
                            vartype='Continuous'):
        """
        transform slice of data by separating our pos/neg errors, aggregating up to the mean of the slice
        and returning transformed dataset
        :param group: slice of data being operated on
        :param col: current col name needed for continuous transform
        :param vartype: str --> categorical or continuous
        :return: compressed data representation in dataframe object
        """
        assert 'errors' in group.columns, 'errors needs to be present in dataframe slice'
        assert vartype in ['Continuous', 'Categorical'], 'variable type needs to be continuous or categorical'
        # copy so we don't change the og data
        group_copy = group.copy(deep=True)
        # split out positive vs negative errors
        errors = group_copy['errors']
        # create separate columns for pos or neg errors
        errors = concat([errors[errors > 0], errors[errors < 0]], axis=1)
        # rename error columns
        errors.columns = ['errPos', 'errNeg']
        # merge back with original data
        toreturn = concat([group_copy.loc[:, group_copy.columns != 'errors'], errors], axis=1)
        # return the mean
        if vartype == 'Categorical':
            logging.info(""""Returning mean values for group of categorical variable in transform_function
                             \nGroup: {}
                             \nGroup Shape: {}
                             \nCol: {}
                             \nvartype: {}""".format(groupby,
                                                     group.shape,
                                                     col,
                                                     vartype))
            # return the mean of the columns
            return self.aggregate_func(toreturn)
        else:
            logging.info(""""Returning continuous aggregate values in transform_function
                                         \nGroup: {}
                                         \nGroup Shape: {}
                                         \nCol: {}
                                         \nvartype: {}""".format(groupby,
                                                                 group.shape,
                                                                 col,
                                                                 vartype))
            errors = DataFrame({
                                    col: toreturn[col].max(),
                                    groupby: toreturn[groupby].mode(),
                                    'predictedYSmooth': toreturn['predictedYSmooth'].mean(),
                                    'errPos': self.aggregate_func(toreturn['errPos']),
                                    'errNeg': self.aggregate_func(toreturn['errNeg'])})

            return errors

    def _var_check(
                    self,
                    col=None,
                    groupby=None):
        """
        handle continuous and categorical variable types
        :param col: specific column being operated on within dataset -- str
        :param groupby: specific groupby variable being operated on within dataset -- str
        :return: errors dataframe for particular column and groupby variable
        """
        # subset col indices
        col_indices = [col, 'errors', 'predictedYSmooth', groupby]
        # check if categorical
        if is_categorical_dtype(self.cat_df.loc[:, col]):
            logging.info("""Column determined as categorical datatype, transforming data for categorical column
                            \nColumn: {}
                            \nGroup: {}""".format(col, groupby))
            # set variable type
            vartype = 'Categorical'
            # create a partial function from transform_function to fill in column and variable type
            categorical_partial = partial(self._transform_function,
                                          col=col,
                                          groupby=groupby,
                                          vartype=vartype)
            # slice over the groupby variable and the categories within the current column
            errors = self.cat_df[col_indices].groupby([groupby, col]).apply(categorical_partial)
            # final categorical transformations
            errors.reset_index(inplace=True)
            # rename
            errors.rename(columns={groupby: 'groupByValue'}, inplace=True)
            # rename columns based on user featuredict input
            errors.rename(columns=self.featuredict, inplace=True)
            # assign groupby variable to the errors dataframe
            errors['groupByVarName'] = groupby

        else:
            logging.info("""Column determined as continuous datatype, transforming data for continuous column
                                        \nColumn: {}
                                        \nGroup: {}""".format(col, groupby))
            # set variable type
            vartype = 'Continuous'
            # create partial function to fill in col and vartype of _continuous_slice
            cont_slice_partial = partial(self._continuous_slice,
                                         col=col,
                                         vartype=vartype,
                                         groupby=groupby)
            # groupby the groupby variable on subset of columns and apply cont_slice_partial
            errors = self.cat_df[col_indices].groupby(groupby).apply(cont_slice_partial)
            # rename columns based on user featuredict input
            errors.rename(columns=self.featuredict, inplace=True)

        # json out

        errors = errors.replace(np.nan, 'null')
        # convert to json structure
        json_out = utils.to_json(
                                    errors,
                                    vartype=vartype,
                                    html_type='error',
                                    incremental_val=None)
        # return json_out
        return json_out


class WhiteBoxSensitivity(WhiteBoxBase):

    """
    Sensitivity model analysis.

    In the continuous case, increment values by user defined number of standard
    deviations, rerun model predictions, and calculate the average differences
    in original predictions with raw data and new predictions with synthetic data
    for various groups or slices of the original dataset.

    In the categorical case, convert non modal values to the mode and calculate
    model sensitivity based on this adjustment.

    Model sensitivity is the difference between original predictions for unadjusted data
    and synthetic data predictions.

    Parameters

    ----------

    modelobj : sklearn model object
        Used to create predictions for synthetic data

    model_df : pandas DataFrame
        Original raw dataset used to train and calibrate modelobj. This can
        and should in most cases include dummy variables for categorical data columns.

    ydepend : str
        Y dependent variable used to build modelobj

    cat_df : pandas DataFrame
        Raw, unadjusted dataframe with categorical columns converted to pandas
        data type Categorical. These categorical designations are picked up throughout
        and are important for proper functioning of WhiteBoxSensitvitiy

    featuredict : dict
        Optional user defined dictionary to clean up column name and subset
        the outputs to only columns defined in featuredict

    groupbyvars : list
        grouping variables to analyze impact of model for various groups of data. I.e.
        if working on dataset with red and white wine, we can disambiguate how sensitive
        the model is to changes in data for each type of wine

    aggregate_func : function
        function to perform aggregate function to groups of data pertaining to sensitivity
        analysis. I.e. take the median model sensitivity for groups of data.

    verbose : int
        Logging level

    std_num : int
        Number of standard deviations to push data for syntehtic variable creation and senstivity analysis. Appropriate
        values include -3, -2, -1, 1, 2, 3

    See also

    ------------

    WhiteBoxError : analyze how the model errors are doing for various groups of data
    WhiteBoxBase : base class inherited from WhiteBoxSensitivity to perform key functionality
        and grouping logic
    """

    def __init__(self,
                 modelobj,
                 model_df,
                 ydepend,
                 cat_df=None,
                 featuredict=None,
                 groupbyvars=None,
                 aggregate_func=np.median,
                 verbose=0,
                 std_num=1):
        """
        :param modelobj: sklearn model object
        :param model_df: Pandas Dataframe used to build/train model
        :param ydepend: Y dependent variable
        :param cat_df: Pandas Dataframe of raw data - with categorical datatypes
        :param featuredict: Subset and rename columns
        :param groupbyvars: grouping variables
        :param aggregate_func: function to aggregate sensitivity results by group
        :param verbose: Logging level
        :param std_num: Standard deviation adjustment
        """

        if std_num not in [-3, -2, -1, 1, 2, 3]:
            raise ValueError("""Standard deviation adjustment needs to be -3, -2, -1, 1, 2, or 3
                                \nCurrently value: {}""".format(std_num))

        self.std_num = std_num

        super(WhiteBoxSensitivity, self).__init__(
                                                    modelobj,
                                                    model_df,
                                                    ydepend,
                                                    cat_df=cat_df,
                                                    featuredict=featuredict,
                                                    groupbyvars=groupbyvars,
                                                    aggregate_func=aggregate_func,
                                                    verbose=verbose)

    def _transform_function(
                            self,
                            group,
                            groupby='Type',
                            col=None,
                            vartype='Continuous'):
        """
        transform slice of data by separating our pos/neg errors, aggregating up to the mean of the slice
        and returning transformed dataset
        :param group: slice of data being operated on
        :param col: current col name needed for continuous transform
        :param vartype: str --> categorical or continuous
        :return: compressed data representation in dataframe object
        """
        assert 'errors' in group.columns, 'errors needs to be present in dataframe slice'
        assert vartype in ['Continuous', 'Categorical'], 'variable type needs to be continuous or categorical'
        print(group.head())
        if vartype == 'Continuous':
            logging.info(""""Returning aggregate values for group of continuous variable in transform_function of WhiteBoxSensitivity.
                            \nColumn: {}
                            \nGroup: {}
                            \nGroup shape: {}""".format(col, groupby, group.shape))
            # return the max value for the Continuous case
            errors = DataFrame({
                                    col: group[col].max(),
                                    groupby: group[groupby].mode(),
                                    'predictedYSmooth': self.aggregate_func(group['diff'])})
        else:
            logging.info(""""Returning aggregate values for group of categorical variable in transform_function of WhiteBoxSensitvity.
                                        \nColumn: {}
                                        \nGroup: {}
                                        \nGroup shape: {}""".format(col, groupby, group.shape))
            # return the mode for the categorical case
            errors = DataFrame({col: group[col].mode(),
                                groupby: group[groupby].mode(),
                                   'predictedYSmooth': self.aggregate_func(group['diff'])})

        return errors

    def _var_check(
                    self,
                    col=None,
                    groupby=None):
        """
        handle continuous and categorical variable types
        :param col: specific column being operated on within dataset -- str
        :param groupby: specific groupby variable being operated on within dataset -- str
        :return: errors dataframe for particular column and groupby variable
        """
        # subset col indices
        col_indices = [col, 'errors', 'predictedYSmooth', groupby, 'diff']
        # make a copy of the data to manipulate and change values
        copydf = self.model_df.copy(deep=True)
        # check if categorical
        if is_categorical_dtype(self.cat_df.loc[:, col]):
            logging.info("""Column determined as categorical datatype, transforming data for categorical column
                                        \nColumn: {}
                                        \nGroup: {}""".format(col, groupby))
            # set variable type
            vartype = 'Categorical'
            # pull out the categorical dummy columns that match the current column
            all_type_cols = copydf.filter(regex='{}_*'.format(col)).columns
            # find the mode from the original cat_df for this column
            incremental_val = self.cat_df[col].mode().values[0]
            # find the columns within all_type_cols related to the mode_val
            mode_col = list(filter(lambda x: incremental_val in x, all_type_cols))
            # convert mode cols to all 1's
            copydf.loc[:, mode_col] = 1
            # convert all other non mode cols to zeros
            non_mode_col = list(filter(lambda x: incremental_val not in x, all_type_cols))
            copydf.loc[:, non_mode_col] = 0
            # make predictions with the switches to the dataset
            copydf['new_predictions'] = self.modelobj.predict(copydf.loc[:, ~copydf.columns.isin([self.ydepend,
                                                                                                  'predictedYSmooth'])])
            # calculate difference between actual predictions and new_predictions
            self.cat_df['diff'] = copydf['new_predictions'] - copydf['predictedYSmooth']
            # create a partial function from transform_function to fill in column and variable type
            categorical_partial = partial(self._transform_function,
                                          col=col,
                                          groupby=groupby,
                                          vartype=vartype)
            # create mask of data to select rows that are not equal to the mode of the category. This will prevent
            # blank displays in the HTML
            mode_mask = self.cat_df[col] != incremental_val
            # slice over the groupby variable and the categories within the current column
            sensitivity = self.cat_df[mode_mask][col_indices].groupby([groupby, col]).apply(categorical_partial)
            # final categorical transformations
            #sensitivity.reset_index(inplace=True)
            # rename
            sensitivity.rename(columns={groupby: 'groupByValue'}, inplace=True)
            # rename columns based on user featuredict input
            sensitivity.rename(columns=self.featuredict, inplace=True)
            # assign groupby variable to the errors dataframe
            sensitivity['groupByVarName'] = groupby

        else:
            logging.info("""Column determined as continuous datatype, transforming data for continuous column
                                                    \nColumn: {}
                                                    \nGroup: {}""".format(col, groupby))
            # set variable type
            vartype = 'Continuous'
            incremental_val = copydf[col].std() * self.std_num
            # tweak the currently column by the incremental_val
            copydf[col] = copydf[col] + incremental_val
            # make predictions with the switches to the dataset
            copydf['new_predictions'] = self.modelobj.predict(copydf.loc[:, ~copydf.columns.isin([self.ydepend,
                                                                                                  'predictedYSmooth'])])
            # calculate difference between actual predictions and new_predictions
            self.cat_df['diff'] = copydf['new_predictions'] - copydf['predictedYSmooth']
            # create partial function to fill in col and vartype of _continuous_slice
            cont_slice_partial = partial(self._continuous_slice,
                                         col=col,
                                         vartype=vartype,
                                         groupby=groupby)
            # groupby the groupby variable on subset of columns and apply cont_slice_partial
            sensitivity = self.cat_df[col_indices].groupby(groupby).apply(cont_slice_partial)
            # rename columns based on user featuredict input
            sensitivity.rename(columns=self.featuredict, inplace=True)

        # json out
        sensitivity = sensitivity.replace(np.nan, 'null')
        logging.info("""Converting output to json type using to_json utility function""")
        # convert to json structure
        json_out = utils.to_json(sensitivity, vartype=vartype, html_type = 'sensitivity',
                                 incremental_val=incremental_val)
        # return json_out
        return json_out
