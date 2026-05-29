Version 14.0.0.1:
	- Fixed the issue of wrong tax calculation when no discount is given in orderline.
date :2/6/2021
Version: 14.0.0.2
Issues:
    When we apply the discount on the untaxed amount than it is multiplying the tax instead of quantity in invoice when discount applies to global.

date" 8/6/2021
version:14.0.0.3
Issue: In sale Order when Apply discount on order line with the more than 1 qty and create invoice in that not getting proper value of Discount.

date :- 24 sep 2021
version:- '14.0.0.4'
Issue :- In create a new invoice apply discount of global and add a product and add the tax but if we change the
        quantity it will be a not a update of tax base on updated qty, also multi currancy true so confirm invoice
         raise an error. solve the in this two issue.

date:- 20 oct 2021
version :- '14.0.0.5'
Issue :- In create a new invoice create a vendor bill and if conform the bill so getting the user error ,
         solve the user error.

14.0.0.6 ==>fixed issue of multi company for discount and fixed issue of account warning for multi company.


14.0.0.7 ==>fixed issue of discount data are not showing in portal preview of SO.

14.0.0.8 ==>changed float to Monetary type for base fields.

14.0.0.9 ==>fixed issue of down payment in both global and line discount.

14.0.1.0 ==>fixed issue of account warning in settings.

14.0.1.1 ==>fixed all calculation of tax on invoice,bill,credit note and refund in untax discount applied method.

14.0.1.2 ==>fixed issue of global discount when quantity is more than one in invoice,bill,credit note and refund.

14.0.1.3 ==>fixed issue of amount total in tree view.

14.0.1.4 ==> Fixed issue of wehn deliver products in different delivery orders in that case when invoices are generated at that time amount discount calculate wrong.

14.0.1.5 ==> Fixed issue of when select tax and untax at that time show wrong value in discount amount.

14.0.1.6 ==> Fixed issue of "TypeError: _create_invoices() got an unexpected keyword argument 'date'" error display.

14.0.1.7 ==> Remove Branch app from the dependency and other commented code by Siddharth's last commit