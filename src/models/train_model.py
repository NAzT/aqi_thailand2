# -*- coding: utf-8 -*-
from ..imports import *
from ..gen_functions import *
from ..features.dataset import Dataset
from ..visualization.vis_model import *
from .predict_model import *


def load_meta(meta_filename:str):
    """Read model_meta dictionary and return model_meta dicitonary

    Args:
        meta_filename: model meta filename 
      

    Return: dict
        pollutant_meta dictionary for that pollutant 

    """
    if os.path.exists(meta_filename):
        with open(meta_filename) as f:
            model_meta = json.load(f)
    else:
        model_meta = {}

    return model_meta

def save_meta(meta_filename:str, model_meta):
    """Save model_meta

    Args:
        meta_filename: model_meta filename 
        
    Returns(optional): model meta dictionary 
        
    """ 

    with open(meta_filename, 'w') as f:
        json.dump(model_meta, f)

def do_rf_search(x_trn:np.array, y_trn:np.array, cv_split:str='time', n_splits:int=5,param_dict:dict=None, x_tree=False, n_jobs=-2):
    """Perform randomize parameter search for randomforest regressor return the best estimator 
    
    Args: 
        x_trn: 2D array of x data 
        y_trn: 2D np.array of y data
        cv_split(optional): if "time". Use TimeSeriesSplit, which don't shuffle the data.
        n_splits(optional): number of cross validation split [default:5]
        params_dict(optional): search parameter dictionary [default:None]
        x_tree(optional): if True, use ExtraTreesRegressor instead of RandomForestRegressor
        n_jobs(optional): number of CPU use [default:-1]

    Returns: best estimator 
    """
    if x_tree:
        m = GradientBoostingRegressor(random_state=42)
    else:
        # rf 
        m = RandomForestRegressor(random_state=42)
    
    if param_dict==None:
        if x_tree:

            param_dict = {
                'n_estimators':range(20,200,20),
                'min_samples_split' : [2, 5, 10, 20, 50],
                'criterion': ['mse', 'mae'],
                'max_depth': [3, None],
                'max_features' : ['auto','sqrt','log2']}
        else:
            param_dict = {'n_estimators':range(20,200,20),
              'max_depth': [3, None],
              'min_samples_split' : [2, 5, 10, 20, 50], 
              'max_features' : ['auto','sqrt','log2'],
               'bootstrap' : [True, False],
              'min_samples_leaf': range(1, x_trn.shape[1] )}
    
    if cv_split =='time':
        cv = TimeSeriesSplit(n_splits=n_splits)
        
    else:
        cv = n_splits
    #hyper parameter tuning
    search = RandomizedSearchCV(m, param_distributions=param_dict,
                            n_iter=100,n_jobs=n_jobs, cv=cv, random_state=40)

    search.fit(x_trn,y_trn)
    
    print(search.best_params_, search.best_score_)
    
    return search.best_estimator_

def reduce_cols(dataset, x_cols:list, to_drop:list, model,trn_i, val_i):
    """Try droping the columns in to_drop. Keep track of the columns which can be remove from the model.
    
    Args:
        dataset: dataset object
        x_cols: current x columns 
        to_drop: data to drop 
        model: model object to fit and predict
        trn_i: index in dataset.split_list for training data 
        val_i: index in dataset.split_list for validation data
    
    Returns:
        model: fitted model
        x_cols: a list of new x_cols data 
        
    """
    print('old cols length', len(x_cols))
    trn_index = dataset.split_list[trn_i]
    val_index = dataset.split_list[val_i]
    
    for col in to_drop:
        
        xtrn, ytrn, x_cols = dataset.get_data_matrix(use_index=trn_index,x_cols=x_cols)
        xval, yval, _ = dataset.get_data_matrix(use_index=val_index,x_cols=x_cols)
        
        # obtain the baseline data
        model.fit(xtrn, ytrn)
        base_score = cal_scores(yval, model.predict(xval), header_str ='')['r2_score']

        new_cols = x_cols.copy()
        new_cols.remove(col) 
        xtrn, ytrn, new_x_cols = dataset.get_data_matrix(use_index=trn_index,x_cols=new_cols)
        xval, yval, _ =  dataset.get_data_matrix(use_index=val_index,x_cols=new_cols)
     
        model.fit(xtrn,ytrn)
        score = cal_scores(yval, model.predict(xval), header_str ='')['r2_score']
        
        if score> base_score:
            x_cols.remove(col)
            print('drop', col)
            
    # obtain the final model 
    
    xtrn, ytrn, x_cols = dataset.get_data_matrix(use_index=trn_index,x_cols=x_cols)
    xval, yval, _ = dataset.get_data_matrix(use_index=val_index,x_cols=x_cols)
    model.fit(xtrn, ytrn)
    score_dict = cal_scores(yval, model.predict(xval), header_str ='') 
    
    print('use columns', x_cols)
    print('score after dropping columns', score_dict)
    return model, x_cols


def sk_op_fire(dataset, model, trn_index, val_index, wind_range:list=[2,20],shift_range:list=[-72,72],roll_range:list=[24, 240],vis:bool=False, with_lag=False)-> dict:
    """Search for the best fire parameter using skopt optimization 
    
    Args: 
        dataset: dataset object 
        model: model object
        trn_index: datetime index for training set
        val_index: datetime index of validation set 
        wind_range(optional): min and max value of wind speed 
        shift_range(optional): min and max value of shift parameter
        roll_range(optional): min and max value of roll parameter
        vis(optional): if True, also plot the search space
        with_lag(optional): if True optimized the data with lag columns 
        
    Return: fire_dict fire dictionary 
    
    """
    
    # check the baseline 
    _, *args = dataset.merge_fire(dataset.fire_dict)

    if with_lag: 
        print('optimize fire dict with lag columns')
        dataset.data_org = dataset.data[ [dataset.monitor] + dataset.x_cols_org]
        dataset.build_lag(lag_range=np.arange(1, dataset.lag_dict['n_max'], dataset.lag_dict['step']), roll=dataset.lag_dict['roll'])
        
    x_cols = dataset.x_cols
    print('skop_ fire use x_cols', x_cols)
    # establish the baseline 
    xtrn, ytrn, x_cols = dataset.get_data_matrix(use_index= trn_index,x_cols=x_cols)
    xval, yval, _ = dataset.get_data_matrix(use_index=val_index, x_cols=x_cols)
    
    model.fit(xtrn,ytrn)
    best_score = mean_squared_error(yval,model.predict(xval))
    best_fire_dict = dataset.fire_dict
    print('old score', best_score, 'fire dict', best_fire_dict)
    
    print('optimizing fire parameter using skopt optimizer. This will take about 20 mins')
    # build search space 
    wind_speed = Integer(low=wind_range[0], high=wind_range[1], name='wind_speed')
    shift = Integer(low=shift_range[0], high=shift_range[1], name='shift')
    roll = Integer(low=roll_range[0],high=roll_range[1], name='roll')
    
    dimensions = [wind_speed, shift, roll]
    # setup the function for skopt
    @use_named_args(dimensions)
    def fit_with( wind_speed, shift, roll):
        # function to return the score (smaller better)
        fire_dict = { 'w_speed': wind_speed, 
                      'shift': shift,
                      'roll': roll}
        _, *args = dataset.merge_fire(fire_dict)
        
        if with_lag: 
            dataset.data_org = dataset.data[ [dataset.monitor] + dataset.x_cols_org]
            dataset.build_lag(lag_range=np.arange(1, dataset.lag_dict['n_max'], dataset.lag_dict['step']), roll=dataset.lag_dict['roll'])
      
        xtrn, ytrn, x_cols = dataset.get_data_matrix(use_index= trn_index, x_cols=dataset.x_cols)
        xval, yval, _ = dataset.get_data_matrix(use_index=val_index, x_cols=dataset.x_cols)
    
        model.fit(xtrn,ytrn)
        y_pred = model.predict(xval)
    
        return mean_squared_error(yval,y_pred)


    gp_result = gp_minimize(func=fit_with,dimensions=dimensions,n_jobs=-2,random_state=30)
    
    wind_speed, shift, roll = gp_result.x
    score = gp_result.fun
    if score < best_score:
        print('mean_squared_error for the best fire parameters', gp_result.fun)
        best_fire_dict = {'w_speed': int(wind_speed), 'shift': int(shift), 'roll': int(roll)}
        print('new fire dict', best_fire_dict)
        if vis:
            plot_objective(gp_result)
    else:
        print(f'old fire parameter {best_score} is still better than optimized score ={score}' )
        
    return best_fire_dict, gp_result


def op_lag(dataset, model, split_ratio, lag_range=[2, 120], step_range=[1,25]):
    """Search for the best lag parameters using skopt optimization 
    
    Args: 
        dataset: dataset object 
        model: model object
        split_ratio: list of split ratio
        lag_range(optional): min and max value of wind speed 
        step_range(optional): min and max value of shift parameter
        
    Return: fire_dict fire dictionary 
    
    """
    # build search space 
    n_max = Integer(low=lag_range[0], high=lag_range[1], name='n_max')
    step = Integer(low=step_range[0], high=step_range[1], name='step')
    #roll = Categorical([True, False], name='roll')
    dimensions = [n_max, step]
    
    
    # setup the function for skopt
    @use_named_args(dimensions)
    def fit_with(n_max, step):
        # function to return the score (smaller better)
        dataset.build_lag(lag_range=np.arange(1, n_max, step), roll=True)
        dataset.x_cols = dataset.data.columns.drop(dataset.monitor)
        dataset.split_data(split_ratio=split_ratio)
        xtrn, ytrn, x_cols = dataset.get_data_matrix(use_index=dataset.split_list[0], x_cols=dataset.x_cols)
        xval, yval, _ = dataset.get_data_matrix(use_index=dataset.split_list[1], x_cols=dataset.x_cols)
        model.fit(xtrn,ytrn)
        y_pred = model.predict(xval)
        
        
        return mean_squared_error(yval,y_pred)
    
    gp_result = gp_minimize(func=fit_with,dimensions=dimensions,n_jobs=-2,random_state=30)
    n_max, step = gp_result.x
    lag_dict = {'n_max':int(n_max),
                'step':int(step),
                'roll': True}
    score = gp_result.fun
    print('new mean squared error', score, 'using', lag_dict )
    
    return lag_dict, gp_result


def feat_importance(model, x, y, x_cols, score=r2_score, n_iter=20):
    """Computes the feature importance by shuffle the data
    Args:
        model : the model
        x: the training data
        y: target variable
        x_cols: name of the x columns
        metric: either r2_score of mean_squared_error
    
    Returns: feature of importance pd.DataFrame 
    
    """
 
    baseline = score(y, model.predict(x))
     
    imp = []
    imp_std = []
    for i, col in tqdm_notebook(enumerate(x_cols)):
        shuffle = []
        for _ in range(n_iter):
            shuffle_x = x.copy()
            shuffle_x[:,i] = np.random.permutation(shuffle_x[:,i])
            shuffle_score = score(y, model.predict(shuffle_x))
            shuffle.append(shuffle_score)
        imp.append(np.mean(shuffle))
        imp_std.append(np.std(shuffle))
    
    # crate a feature of importance DataFrame
    fea_imp = pd.DataFrame({'index': x_cols, 'importance':imp,'imp_std':imp_std})
    # normalized 
    if score.__name__ == 'r2_score':
        fea_imp['importance'] = (baseline - fea_imp['importance'])/baseline
    elif score.__name__ == 'mean_squared_error':
        fea_imp['importance'] = (-baseline + fea_imp['importance'])/baseline
    
    return fea_imp.sort_values('importance', ascending=False).reset_index(drop=True)


def train_city_s1(city:str='Chiang Mai', pollutant:str='PM2.5', build=False, model=None, fire_dict=None, x_cols_org=[], lag_dict=None,x_cols=[],rolling_win=True):
    """Training pipeline from process raw data, hyperparameter tune, and save model.

        #. If build True, build the raw data from files 
        #. Process draw data into data using default values
        #. Optimization 1: optimize for the best randomforest model 
        #. Optimization 2: remove unncessary columns 
        #. Optimization 3: find the best fire feature 
        #. Optimization 4: optimize for lag columns
        #. Optimization 5: drop unncessary lag columns
        #. Optimization 6: optimize for the best RF again  
        #. Build pollution meta and save

    Args:
        city: city name
        pollutant(optional): pollutant name
        build(optional): if True, also build the data
        model(optional):
        op_fire(optional):
        x_cols_org(optional):
        lag_dict(optional):
        x_cols(optional):

    Returns: 
        dataset
        model
        poll_meta(dict) 

    """

    data = Dataset(city)
    # remove . from pollutant name for saving file
    poll_name = pollutant.replace('.','')
    if build:
        # build data from scratch 
        data.build_all_data(build_fire=True,build_holiday=False)
    
    # load raw data 
    data.load_()
    if rolling_win:
        rolling_win = data.roll_dict[pollutant]
    else:
        rolling_win = 1
    print('rolling_win ', rolling_win)
    # build the first dataset 
    data.feature_no_fire(pollutant=pollutant, rolling_win=rolling_win)
    if fire_dict==None:
        # use default fire feature
        fire_cols, *args = data.merge_fire()
    else:
        data.fire_dict = fire_dict 
        fire_cols, *args = data.merge_fire(data.fire_dict)
    data.monitor = data.pollutant = pollutant
    

    #. Optimization 1: optimize for the best randomforest model 

    if (model==None) or ( len(x_cols_org) == 0):
        # split the data into 4 set
        print('=================optimize 1: find the best RF model=================')
        data.split_data(split_ratio=[0.40, 0.3, 0.3])
        xtrn, ytrn, x_cols = data.get_data_matrix(use_index=data.split_list[0] )
        xval, yval, _ = data.get_data_matrix(use_index=data.split_list[1])
        data.x_cols = x_cols

        model = do_rf_search(xtrn,ytrn, cv_split='other')
        score_dict = cal_scores(yval, model.predict(xval), header_str ='val_')
        print('optimize 1 score', score_dict)    

        print('=================optimize 2: remove unncessary columns=================')
        importances = model.feature_importances_
        feat_imp = pd.DataFrame(importances, index=x_cols, columns=['importance']) 
        feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()
        show_fea_imp(feat_imp, filename=data.report_folder + f'{poll_name}_fea_imp_op1.png', title='rf feature of importance(raw)')
        
        # columns to consider droping are columns with low importance
        to_drop = feat_imp['index']
        to_drop = [a for a in to_drop if 'fire' not in a]
        for s in ['Humidity(%)','Temperature(C)','Wind Speed(kmph)']:
            to_drop.remove(s)
        to_drop.reverse()
        model, x_cols_org = reduce_cols(dataset=data,x_cols=data.x_cols,to_drop=to_drop,model=model,trn_i=0, val_i=1)
   
    
    if fire_dict==None:
        print('================= optimization 3: find the best fire feature ===================')
        data.fire_dict, gp_result  = sk_op_fire(data, model, trn_index=data.split_list[0], val_index=data.split_list[1])
        fire_cols, *args = data.merge_fire(data.fire_dict)

    if lag_dict==None:
        print('================= optimization 4: improve model performance by adding lag columns =================')
        # prepare no-lag columns 
        data.x_cols_org = x_cols_org  
        data.data_org = data.data[ [data.monitor] + data.x_cols_org]
        print('model parameters', model.get_params())
        # look for the best lag 
        #data.lag_dict, gp_result = op_lag(data, model, split_ratio=[0.45, 0.25, 0.3])
        data.lag_dict, gp_result = op_lag(data, model, split_ratio=[0.45, 0.25, 0.3])
        #data.lag_dict = {'n_max': 2, 'step': 5}
        data.build_lag(lag_range=np.arange(1, data.lag_dict['n_max'], data.lag_dict['step']), roll=data.lag_dict['roll'])
        #print('data.column with lag', data.data.columns)
        data.x_cols = data.data.columns.drop(data.monitor)

        print('x_cols', data.x_cols)
        data.split_data(split_ratio=[0.45, 0.25, 0.3])
        xtrn, ytrn, data.x_cols = data.get_data_matrix(use_index=data.split_list[0], x_cols=data.x_cols)
        xval, yval, _ = data.get_data_matrix(use_index=data.split_list[1], x_cols=data.x_cols)
        xtest, ytest, _ = data.get_data_matrix(use_index=data.split_list[2], x_cols=data.x_cols)
        print('xtrn has shape', xtrn.shape)
        model.fit(xtrn,ytrn)
        score_dict = cal_scores(yval, model.predict(xval), header_str = 'val_')
        print('op4 score', score_dict)
        print('op4 test score', cal_scores(ytest, model.predict(xtest), header_str='test_'))

        print('================= optimization 5: remove unncessary lag columns =================')
        importances = model.feature_importances_
        feat_imp = pd.DataFrame(importances, index=data.x_cols, columns=['importance']) 
        feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()

        # optimize 1 drop unuse cols 
        to_drop = feat_imp['index'].to_list()
        no_drop = ['Humidity(%)','Temperature(C)','Wind Speed(kmph)']  + [a for a in data.x_cols_org if 'fire' in a]
        for s in no_drop:
            to_drop.remove(s)
        to_drop.reverse()
        model, data.x_cols = reduce_cols(dataset=data,x_cols=data.x_cols,to_drop=to_drop,model=model,trn_i=0, val_i=1)
         
    else:
        data.lag_dict = lag_dict
        data.x_cols_org = x_cols_org
        data.data_org = data.data[ [data.monitor] + data.x_cols_org]
        data.build_lag(lag_range=np.arange(1, data.lag_dict['n_max'], data.lag_dict['step']), roll=True)
        data.x_cols = x_cols
        
    # print('================= optimization 7: optimize for the best fire dict again =================')

    # xtrn, ytrn, data.x_cols = data.get_data_matrix(use_index=data.split_list[0],x_cols=data.x_cols)
    # xval, yval, _ = data.get_data_matrix(use_index=data.split_list[1],x_cols=data.x_cols)
    # xtest, ytest, _ = data.get_data_matrix(use_index=data.split_list[2], x_cols=data.x_cols)
    # print('val score before op7', cal_scores(yval, model.predict(xval), header_str='val_'))
    # print('test score before op7', cal_scores(ytest, model.predict(xtest), header_str='test_'))

    # data.fire_dict, gp_result  = sk_op_fire(data, model, trn_index=data.split_list[0], val_index=data.split_list[1], with_lag=True)
    # _, *args = data.merge_fire(data.fire_dict)
    # data.data_org = data.data[ [data.monitor] + data.x_cols_org]
    # data.build_lag(lag_range=np.arange(1, data.lag_dict['n_max'], data.lag_dict['step']), roll=data.lag_dict['roll'])
    
    print('================= optimization 8: optimize for the best rf again =================')
    data.split_data(split_ratio=[0.45, 0.25, 0.3])
     
    #print('x_cols in op7', data.x_cols)
    xtrn, ytrn, data.x_cols = data.get_data_matrix(use_index=data.split_list[0],x_cols=data.x_cols)
    xval, yval, _ = data.get_data_matrix(use_index=data.split_list[1],x_cols=data.x_cols)
    xtest, ytest, _ = data.get_data_matrix(use_index=data.split_list[2], x_cols=data.x_cols)
    print('val score before refit', cal_scores(yval, model.predict(xval), header_str='val_'))
    print('test score before refit', cal_scores(ytest, model.predict(xtest), header_str='test_'))
    
    #model = do_rf_search(xtrn, ytrn,cv_split='other')
    #score_dict = cal_scores(yval, model.predict(xval), header_str ='val_')
    
    #print('val score after op8', cal_scores(yval, model.predict(xval), header_str='val_'))
    #print('test score after op8', cal_scores(ytest, model.predict(xtest), header_str='test_'))

    # final split 
    data.split_data(split_ratio=[0.7, 0.3])
    xtrn, ytrn, data.x_cols = data.get_data_matrix(use_index=data.split_list[0],x_cols=data.x_cols)
    xtest, ytest, _ = data.get_data_matrix(use_index=data.split_list[1],x_cols=data.x_cols)
    model.fit(xtrn,ytrn)
    score_dict = cal_scores(ytest, model.predict(xtest), header_str ='test_')
    print('final score for test set', score_dict)
    

    pickle.dump(model, open(data.model_folder +f'{poll_name}_rf_model.pkl', 'wb'))

    # build feature of importance using build in rf
    try: 
        importances = model.feature_importances_
        feat_imp = pd.DataFrame(importances, index=data.x_cols, columns=['importance']) 
        feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()
        #show_fea_imp(feat_imp,filename=data.report_folder + f'{poll_name}_rf_fea_op2.png', title='rf feature of importance(default)')
    except:
        # custom feature of importance
        feat_imp = feat_importance(model,xtrn,ytrn,data.x_cols,n_iter=50)
        #show_fea_imp(feat_imp,filename=data.report_folder + f'{poll_name}_rf_fea_op2.png', title='rf feature of importance(shuffle)')

    # obtain feature of importance without lag 
    feat_imp['index'] = feat_imp['index'].str.split('_lag_', expand=True)[0]
    feat_imp = feat_imp.groupby('index').sum()
    feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()
    show_fea_imp(feat_imp,filename=data.report_folder + f'{poll_name}_rf_fea_op2_nolag.png', title='rf feature of importance(final)')

    poll_meta =  { 'x_cols_org': data.x_cols_org,
                    'x_cols': data.x_cols,
                    'fire_cols': fire_cols,
                    'fire_dict': data.fire_dict,
                    'lag_dict': data.lag_dict,
                    'rf_score': score_dict,
                    'rf_params': model.get_params(),
                    'rolling_win':rolling_win}

    model_meta = load_meta(data.model_folder + 'model_meta.json')
    model_meta[pollutant] = poll_meta
    save_meta(data.model_folder + 'model_meta.json', model_meta)

    data.save_()
     
    return data, model, poll_meta

    
def load_model1(city:str='Chiang Mai', pollutant:str='PM2.5', build=False, split_list=[0.45, 0.25, 0.3], update=True):

    """Load and update the model without optimization steps. Use parameters from model_meta file. 

    Use for small data update without parameters change.

    Args:
        city:
        pollutant: 
        split_list: datasplit for training and testset  
    
    Returns: 
        model: model 
        dataset: dataset object
        fire_cols:
    
    """

    data = Dataset(city)
    data.monitor = data.pollutant = pollutant
    # remove . from pollutant name for saving file
    poll_name = pollutant.replace('.','')
    # load model_meta 
    model_meta = load_meta(data.model_folder + 'model_meta.json')
    poll_meta = model_meta[pollutant] 

    # load model 
    model = pickle.load(open(data.model_folder +f'{poll_name}_rf_model.pkl','rb'))

    if build:
            # build data from scratch 
            data.build_all_data(build_fire=True,build_holiday=False)
    # load raw data 
    data.load_()
    # build the first dataset 
    print('rolling_win', poll_meta['rolling_win'])
    data.feature_no_fire(rolling_win=poll_meta['rolling_win'])
    data.fire_dict = poll_meta['fire_dict']
    fire_cols, zone_list = data.merge_fire(data.fire_dict)

    #print('\n fire_columns', fire_cols)
    # build lag_data
    data.lag_dict = poll_meta['lag_dict']
    data.x_cols_org = poll_meta['x_cols_org']
    #print('\n x_cols_org', data.x_cols_org)
    data.data_org = data.data[ [data.monitor] + data.x_cols_org]
    data.build_lag(lag_range=np.arange(1, data.lag_dict['n_max'], data.lag_dict['step']), roll=data.lag_dict['roll'])
    data.x_cols = poll_meta['x_cols']
    #print('\n x_cols', data.x_cols)

    
    # split data
    data.split_data(split_ratio=split_list)
    trn_index = data.split_list[0]
    test_index = data.split_list[1]
         
    xtrn, ytrn, data.x_cols = data.get_data_matrix(use_index=trn_index,x_cols=data.x_cols)
    xtest, ytest, _ = data.get_data_matrix(use_index=test_index,x_cols=data.x_cols)
        
    if update:
        model.fit(xtrn, ytrn)
    
    print('raw model performance', cal_scores(ytest, model.predict(xtest), header_str ='test_'))

    # calculate the average error
    trn_error = cal_error(data, model, data_index=trn_index)
    # resample
    ytrn_pred_df_avg = trn_error.resample('d').mean().dropna()
    print('daily avg training error', cal_scores(ytrn_pred_df_avg['actual'].values, ytrn_pred_df_avg['pred'].values, header_str='avg_trn_'))

    # calculate the average error
    ytest_pred_df = cal_error(data, model, data_index=test_index)
    # resample
    ytest_pred_df_avg = ytest_pred_df.resample('d').mean().dropna()
    print('daily avg test error', cal_scores(ytest_pred_df_avg['actual'].values, ytest_pred_df_avg['pred'].values, header_str='avg_test_'))

    # obtain feature of importance without lag 
    importances = model.feature_importances_
    feat_imp = pd.DataFrame(importances, index=data.x_cols, columns=['importance']) 
    feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()
    feat_imp['index'] = feat_imp['index'].str.split('_lag_', expand=True)[0]
    feat_imp = feat_imp.groupby('index').sum()
    feat_imp = feat_imp.sort_values('importance',ascending=False).reset_index()

    return data, model, fire_cols, zone_list, feat_imp, poll_meta['rolling_win']

