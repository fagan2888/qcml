function ecos_creator()
    solver_type = {'cvxsocp','ecos','conelp', 'C'};
    
    try
        for i = 1:length(solver_type),
            create_solver('least_squares', solver_type{i});
            % create_solver('geometric_mean');
            create_solver('lp', solver_type{i});
            create_solver('pathological_lp', solver_type{i});
            % create_solver('quadratic_over_linear');
            % create_solver('inv_prob');
            % create_solver('min_max');
            create_solver('robust_ls', solver_type{i});
            % create_solver('ecos_mpc');
            create_solver('lasso', solver_type{i});
            create_solver('portfolio', solver_type{i});
            create_solver('svm', solver_type{i});
            % create_solver('chebyshev');
        end
    catch e
        cd ..   % return to top level directory
        e.message
    end 
end

function create_solver(directory, language)
    s = sprintf('Creating %s solver for %s.', upper(language), upper(directory));
    fprintf('%s\n',s);
    divider = s;
    for i = 1:length(divider)
        divider(i) = '=';
    end
    fprintf('%s\n',divider);
    
    cd(directory);
    
    try
        tic;
        switch lower(language)
            case 'cvxsocp'
                [status, result] = system(['../../src/efe --cvxsocp ' directory '.prob']);
                copyfile([directory '/solver.m'], 'cvxsocp_solver.m', 'f');
            case 'ecos'
                [status, result] = system(['../../src/efe --ecos ' directory '.prob']);
                copyfile([directory '/solver.m'], 'ecos_solver.m', 'f');
            case 'conelp'
                [status, result] = system(['../../src/efe --conelp ' directory '.prob']);
                copyfile([directory '/solver.m'], 'conelp_solver.m', 'f');
            case 'c'
                [status, result] = system(['../../src/efe --C ' directory '.prob']);
                cd(directory);
                try
                    evalc('makemex');
                catch e
                    cd ..
                    throw(e);
                end
                cd ..
                copyfile([directory '/efe_solve.' mexext]);
            otherwise
                [status, result] = system(['../../src/efe --ecos ' directory '.prob']);            
                copyfile([directory '/solver.m'], 'ecos_solver.m', 'f');
        end
        fprintf('  Took %f seconds to generate solver.\n\n', toc);
    catch e
        cd ..
        throw(e);
    end

    cd ..
end