# sensitivity plot creation and testing

from sklearn.ensemble import RandomForestRegressor
import pandas as pd
from whitebox import utils
import numpy as np
from whitebox.WhiteBox import WhiteBoxSensitivity

#====================
# wine quality dataset example
# featuredict - cat and continuous variables

# read in wine quality dataset
wine = pd.read_csv('./data/winequality.csv')
# init randomforestregressor
modelObjc = RandomForestRegressor()

###
#
# Specify model parameters
#
###
yDepend = 'quality'
# create second categorical variable by binning
wine['volatile.acidity.bin'] = wine['volatile.acidity'].apply(lambda x: 'bin_0' if x > 0.29 else 'bin_1')
# specify groupby variables
groupbyVars = ['Type', 'volatile.acidity.bin']
# subset dataframe down
wine_sub = wine.copy(deep = True)
# select all string columns so we can convert to pandas Categorical dtype
string_categories = wine_sub.select_dtypes(include = ['O'])
# iterate over string categories
for cat in string_categories:
    wine_sub[cat] = pd.Categorical(wine_sub[cat])

# create train dataset for fitting model
xTrainData = wine_sub.loc[:, wine_sub.columns != yDepend].copy(deep = True)
# convert all the categorical columns into their category codes
xTrainData = utils.convert_categorical_independent(xTrainData)
yTrainData = wine_sub.loc[:, yDepend]

modelObjc.fit(xTrainData, yTrainData)

# specify featuredict as a subset of columns we want to focus on
featuredict = {'fixed.acidity': 'FIXED ACIDITY',
               'Type': 'TYPE',
               'quality': 'SUPERQUALITY',
               'volatile.acidity.bin': 'VOLATILE ACIDITY BINS',
               'AlcoholContent': 'AC',
               'sulphates': 'SULPHATES'}


# create dummies example using all categorical columns
dummies = pd.concat([pd.get_dummies(wine_sub.loc[:, col], prefix = col) for col in wine_sub.select_dtypes(include = ['category']).columns], axis = 1)
finaldf = pd.concat([wine_sub.select_dtypes(include = [np.number]), dummies], axis = 1)

# fit the model using the dummy dataframe
modelObjc.fit(finaldf.loc[:, finaldf.columns != yDepend], finaldf.loc[:, yDepend])

# instantiate whitebox sensitivity
WB = WhiteBoxSensitivity(modelobj = modelObjc,
                   model_df = finaldf,
                   ydepend= yDepend,
                   cat_df = wine_sub,
                   groupbyvars = groupbyVars,
                   featuredict = featuredict)
# run
WB.run()

wine_sub['errors'] = np.random.rand(wine_sub.shape[0], 1)
wine_sub['predictedYSmooth'] = np.random.rand(wine_sub.shape[0], 1)
wine_sub['diff'] = np.random.rand(wine_sub.shape[0], 1)

results = WB.continuous_slice(wine_sub.groupby('AlcoholContent').get_group('Low'),
                    groupby='Type',
                    col='sulphates',
                    vartype='Continuous')

WB.var_check(col = 'sulphates',
             groupby='Type')

results.head()

# save the final outputs to disk
WB.save(fpath = './output/wine_quality_sensitivity.html')